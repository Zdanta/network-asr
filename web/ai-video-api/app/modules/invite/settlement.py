"""Rewards derive from a trusted SKU price snapshot and verified payment observation."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from threading import Event, Thread
import logging

from sqlalchemy import or_, select

from app.core.database import get_session_factory
from app.models.opcpay import OpcpayOperation, OpcpayTrialClaim
from app.models.invite import InviteRecord
from app.models.user import User

logger = logging.getLogger(__name__)


def reconcile_purchase(db, biz_no: str, observation: dict):
    if (observation.get("status") not in {"PAID", "REFUNDED"}
            or observation.get("status_source") != "ALIPAY_PURCHASE_QUERY_V3"
            or not observation.get("checked_at")):
        return
    try:
        checked = datetime.fromisoformat(observation["checked_at"].replace("Z", "+00:00"))
        if checked.tzinfo is None:
            return
        checked = checked.astimezone(timezone.utc).replace(tzinfo=None)
        if checked > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5):
            return
    except (ValueError, TypeError):
        return
    op = db.scalar(select(OpcpayOperation).where(OpcpayOperation.biz_no == biz_no, OpcpayOperation.kind == "PURCHASE"))
    if (op is None or not op.metadata_json or observation.get("user_id") != str(op.user_id)
            or observation.get("idempotency_key") != op.biz_no):
        return
    meta = json.loads(op.metadata_json)
    inviter_id = meta.get("inviter_id")
    if inviter_id is not None:
        # All reward/withdrawal balance changes serialize on the inviter row first.
        inviter = db.scalar(select(User).where(User.id == inviter_id).with_for_update())
        if inviter is None or inviter.id == op.user_id:
            return
    op = db.scalar(select(OpcpayOperation).where(OpcpayOperation.id == op.id).with_for_update()
                   .execution_options(populate_existing=True))
    meta = json.loads(op.metadata_json)
    previous_checked = datetime.fromisoformat(meta["checked_at"]) if meta.get("checked_at") else None
    if previous_checked and checked < previous_checked:
        db.rollback()
        return
    if meta.get("payment_status") == "REFUNDED" and observation["status"] != "REFUNDED":
        db.rollback()
        return
    meta["payment_status"], meta["checked_at"] = observation["status"], checked.isoformat()
    if observation["status"] == "PAID" and not meta.get("paid_confirmed_at"):
        # Freeze first confirmation; later polling must not move revenue into another day.
        meta["paid_confirmed_at"] = previous_checked.isoformat() if previous_checked else checked.isoformat()
    claim = db.scalar(select(OpcpayTrialClaim).where(OpcpayTrialClaim.user_id == op.user_id,
        OpcpayTrialClaim.order_no == op.biz_no).with_for_update())
    if claim and claim.paid_at is None:
        # A refund also proves this trial was purchased; eligibility is not reset.
        claim.paid_at = checked
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    record = db.scalar(select(InviteRecord).where(InviteRecord.trigger_order_no == biz_no).with_for_update())
    if observation["status"] == "REFUNDED":
        if record:
            record.reward_status = "REVERSED"
            record.remark = "支付宝核验退款，返现已撤回"
    elif inviter_id is not None:
        price = Decimal(meta["price"]).quantize(Decimal("0.01"))
        rate = min(max(Decimal(str(meta["rate"])), 0), 100)
        reward = (price * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        if not meta.get("release_at"):
            meta["release_at"] = (now + timedelta(days=max(0, int(meta.get("hold_days", 7))))).isoformat()
        if record is None and reward > 0:
            record = InviteRecord(inviter_id=inviter_id, invitee_id=op.user_id, reward_type="CASH", reward_value=0,
                recharge_amount=price, reward_amount=reward, reward_status="PENDING", trigger_order_no=biz_no,
                remark="已核验支付，按套餐标价计算，等待冻结期结束")
            db.add(record)
        if record and record.reward_status != "REVERSED":
            # An old observation cannot release a reward merely because time passed.
            if now >= datetime.fromisoformat(meta["release_at"]) and now - timedelta(hours=24) <= checked <= now + timedelta(minutes=5):
                record.reward_status, record.remark = "SUCCESS", "冻结期结束，已再次核验支付状态"
    op.metadata_json = json.dumps(meta)
    db.commit()


class SettlementWorker:
    def __init__(self):
        self.event, self.thread = Event(), None

    def start(self):
        self.event.clear()
        self.thread = Thread(target=self.run, name="invite-settlement", daemon=True)
        self.thread.start()

    def run(self):
        while not self.event.is_set():
            try:
                with get_session_factory()() as db:
                    operations = list(db.scalars(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE",
                        OpcpayOperation.metadata_json.is_not(None),
                        OpcpayOperation.created_at >= datetime.now() - timedelta(days=30),
                        or_(OpcpayOperation.lease_until.is_(None), OpcpayOperation.lease_until < datetime.now()))
                        .order_by(OpcpayOperation.lease_until, OpcpayOperation.id).limit(10)))
                    ids = [(op.user_id, op.biz_no, op.id) for op in operations]
                from app.modules.payment.opcpay_service import OpcpayService
                for user_id, biz_no, op_id in ids:
                    if self.event.is_set():
                        break
                    with get_session_factory()() as db:
                        op = db.get(OpcpayOperation, op_id)
                        op.lease_until = datetime.now() + timedelta(minutes=15)
                        db.commit()
                        try:
                            OpcpayService(db).transaction(user_id, biz_no)
                        except Exception:
                            logger.warning("payment settlement awaiting next observation, orderNo=%s", biz_no)
            except Exception:
                logger.warning("invite settlement unavailable; check migration and database")
            self.event.wait(60)

    def stop(self):
        self.event.set()
        if self.thread:
            self.thread.join(timeout=2)


settlement_worker = SettlementWorker()
