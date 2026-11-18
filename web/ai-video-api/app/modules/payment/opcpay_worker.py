"""Durable task/outbox boundary, with a renewable lease and unique delivery receipt."""
import json
import logging
import uuid
from datetime import datetime, timedelta
from threading import Event, Thread

from sqlalchemy import or_, select, update

from app.core.database import get_session_factory
from app.core.exceptions import AppException
from app.models.opcpay import OpcpayOperation
from app.models.task import Task
from app.modules.payment.opcpay_client import OpcpayClient, confirmed_consumption

logger = logging.getLogger(__name__)


def process_opcpay_task(task_no: str) -> bool:
    factory = get_session_factory()
    with factory() as db:
        op = db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "CONSUME", OpcpayOperation.biz_no == task_no))
        if op is None:
            return False
        if op.state != "PENDING":
            return True
        owner = uuid.uuid4().hex
        claimed = db.execute(update(OpcpayOperation).where(OpcpayOperation.id == op.id,
            OpcpayOperation.state == "PENDING",
            or_(OpcpayOperation.lease_until.is_(None), OpcpayOperation.lease_until < datetime.now()))
            .values(lease_owner=owner, lease_until=datetime.now() + timedelta(minutes=5)))
        db.commit()
        if claimed.rowcount != 1:
            return True
        op_id = op.id

    stopped = Event()

    def renew():
        while not stopped.wait(30):
            try:
                with factory() as heartbeat:
                    heartbeat.execute(update(OpcpayOperation).where(OpcpayOperation.id == op_id,
                        OpcpayOperation.lease_owner == owner).values(lease_until=datetime.now() + timedelta(minutes=5)))
                    heartbeat.commit()
            except Exception:
                # No provider exceptions, credentials or response bodies in logs.
                logger.warning("opcpay lease renewal delayed, taskNo=%s", task_no)

    heartbeat_thread = Thread(target=renew, daemon=True)
    heartbeat_thread.start()
    try:
        with factory() as db:
            op = db.get(OpcpayOperation, op_id)
            task = db.scalar(select(Task).where(Task.task_no == task_no))
            if task is None:
                return True
            request = json.loads(op.request_json)
            body = request["body"]
            if op.result_text is None:
                task.status = "PROCESSING"
                task.progress = 10
                task.start_time = datetime.now()
                db.commit()
                # Existing media and ASR modules; no transaction during external work.
                from app.modules.task.worker import _load_task_and_file, _extract_audio, _run_asr
                _, file_record = _load_task_and_file(db, task_no)
                db.commit()
                try:
                    from app.modules.guest.service import GuestService
                    GuestService(db).before_asr(task_no)
                    audio = _extract_audio(file_record)
                    text = _run_asr(file_record, audio)
                except Exception:
                    db.rollback()
                    op = db.scalar(select(OpcpayOperation).where(OpcpayOperation.id == op_id).with_for_update()
                                   .execution_options(populate_existing=True))
                    if op.lease_owner != owner:
                        db.rollback()
                        return True
                    op.state = "FAILED"
                    task.status = "FAIL"
                    task.error_msg = "转写失败，未发起积分核销，请重新提交素材"
                    GuestService(db).settle(task_no, False)
                    db.commit()
                    return True
                # Fence a stale worker before persisting its staged result.
                current = db.scalar(select(OpcpayOperation).where(OpcpayOperation.id == op_id).with_for_update()
                                    .execution_options(populate_existing=True))
                if current.lease_owner != owner:
                    db.rollback()
                    return True
                op.result_text = text
                task.audio_url = audio
                task.progress = 85
                db.commit()
            # Original request parameters never change on retries, even if pricing changes.
            db.commit()
            local_source = request.get("source") == "LOCAL"
            response = None if local_source else OpcpayClient().request("/consume", body)
            current = db.scalar(select(OpcpayOperation).where(OpcpayOperation.id == op_id).with_for_update()
                                .execution_options(populate_existing=True))
            if current.lease_owner != owner:
                db.rollback()
                return True
            if local_source:
                from app.modules.quota.service import QuotaService
                try:
                    QuotaService(db).consume_points_once(task.user_id, body["amount"], task_no, "历史本地额度转写消耗")
                except AppException as exc:
                    if exc.code != 2001:
                        raise
                    op.state = "FAILED"
                    task.status = "FAIL"
                    task.error_msg = "本地积分已不足，本次未扣费；请补充额度后重新上传"
                    db.commit()
                    return True
                except Exception:
                    db.rollback()
                    raise
                response = {"status": "SUCCEEDED", "confirmed": True, "idempotency_key": task_no,
                            "consumed": body["amount"], "quota_unit": request["unit"]}
            op.response_json = json.dumps(response)
            if confirmed_consumption(response, body, request["unit"]):
                from app.models.quota import QuotaLog
                remaining = response.get("remaining")
                if not local_source and type(remaining) is int and remaining >= 0:
                    db.add(QuotaLog(user_id=task.user_id, change_type="CONSUME", change_amount=-body["amount"],
                        before_points=remaining + body["amount"], after_points=remaining,
                        biz_no=task_no, remark="一人付：按素材时长核销积分"))
                # Receipt and delivery are committed together; no earlier API exposes staged text.
                task.raw_text = op.result_text
                task.status = "SUCCESS"
                task.progress = 100
                task.error_msg = None
                task.finish_time = datetime.now()
                op.state = "DELIVERED"
            elif response.get("status") == "FAILED":
                task.status = "FAIL"
                task.error_msg = "积分核销失败，文稿未交付，请联系管理员核实原任务"
                op.state = "FAILED"
            else:
                task.error_msg = "积分核销待确认，系统将使用原任务编号恢复，请勿重复提交"
            db.commit()
    except Exception:
        logger.warning("opcpay task awaiting recovery, taskNo=%s", task_no)
    finally:
        stopped.set()
        heartbeat_thread.join(timeout=2)
        with factory() as db:
            db.execute(update(OpcpayOperation).where(OpcpayOperation.id == op_id,
                OpcpayOperation.lease_owner == owner).values(lease_until=datetime.now() + timedelta(seconds=30), lease_owner=None))
            db.commit()
    return True


class OpcpayRecovery:
    def __init__(self):
        self.stop_event = Event()
        self.thread = None

    def start(self):
        self.stop_event.clear()
        self.thread = Thread(target=self.run, daemon=True, name="opcpay-recovery")
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                with get_session_factory()() as db:
                    tasks = list(db.scalars(select(OpcpayOperation.biz_no).where(
                        OpcpayOperation.kind == "CONSUME", OpcpayOperation.state == "PENDING",
                        or_(OpcpayOperation.lease_until.is_(None), OpcpayOperation.lease_until < datetime.now()))
                        .order_by(OpcpayOperation.id).limit(50)))
                from app.workers.task_queue import task_worker_queue
                for task_no in tasks:
                    task_worker_queue.enqueue_task(task_no)
            except Exception:
                logger.warning("opcpay recovery unavailable; check migration and database")
            self.stop_event.wait(30)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)


opcpay_recovery = OpcpayRecovery()
