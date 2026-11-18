import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from threading import Event, Thread

import httpx
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models
from app.core.database import Base
from app.core.exceptions import AppException
from app.models.file import FileRecord
from app.models.opcpay import OpcpayOperation
from app.models.quota import QuotaLog, UserQuota
from app.models.task import Task
from app.modules.payment.opcpay_client import OpcpayClient, confirmed_consumption
from app.modules.payment.opcpay_router import PurchaseRequest
from app.modules.payment.opcpay_service import OpcpayService
from app.modules.payment.opcpay_worker import process_opcpay_task


BODY = {"user_id": "7", "idempotency_key": "TASK-test", "amount": 10, "reason": "音视频转写"}


def success(body):
    return {"status": "SUCCEEDED", "confirmed": True, "idempotency_key": body["idempotency_key"],
            "consumed": body["amount"], "quota_unit": "POINT", "remaining": 90}


class OpcpayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "test.db"))
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.factory_patch = patch("app.modules.payment.opcpay_worker.get_session_factory", return_value=self.factory)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)

    def seed(self):
        with self.factory() as db:
            file = FileRecord(file_no="FILE-test", user_id=7, source_file_name="test.mp4", storage_file_name="test.mp4",
                              file_type="VIDEO", file_url="test.mp4", file_size=10, duration_seconds=60)
            db.add(file)
            db.flush()
            db.add(Task(task_no="TASK-test", user_id=7, file_id=file.id, file_url=file.file_url))
            db.add(OpcpayOperation(kind="CONSUME", user_id=7, action_id=file.file_no, biz_no="TASK-test",
                request_json=json.dumps({"body": BODY, "unit": "POINT"}), state="PENDING"))
            db.commit()

    def make_due(self):
        with self.factory() as db:
            op = db.scalar(select(OpcpayOperation))
            op.lease_until = datetime.now() - timedelta(seconds=1)
            db.commit()

    def test_consume_requires_exact_confirmed_receipt(self):
        self.assertTrue(confirmed_consumption(success(BODY), BODY, "POINT"))
        for replacement in ({"status": "UNKNOWN"}, {"confirmed": False}, {"consumed": 1},
                            {"quota_unit": "COUNT"}, {"idempotency_key": "other"}, {"consumed": True}):
            self.assertFalse(confirmed_consumption(success(BODY) | replacement, BODY, "POINT"))

    def test_forged_identity_price_and_amount_rejected(self):
        for extra in ({"user_id": "other"}, {"amount": 1}, {"price": "0.01"}, {"callbackURL": "https://evil.invalid"}):
            with self.assertRaises(ValidationError):
                PurchaseRequest.model_validate({"actionId": "test-action", "skuId": "test-sku"} | extra)

    def test_authenticated_http_contract_and_anonymous_denial(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from app.core.security import get_current_user
        from app.core.exceptions import register_exception_handlers
        from app.modules.payment.opcpay_router import router
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1/payment/opcpay")
        def db_override():
            with self.factory() as db:
                yield db
        app.dependency_overrides[get_db] = db_override
        client = TestClient(app)
        self.assertEqual(client.get("/api/v1/payment/opcpay/catalog").status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, is_guest=False)
        payload = {"enabled": True, "billingMode": "QUANTITY", "quotaUnit": "POINT", "transactionQuery": True,
                   "plans": [{"skuId": "test-sku", "name": "测试", "price": "1.00", "quantity": 10}]}
        with patch.object(OpcpayService, "catalog", return_value=payload):
            response = client.get("/api/v1/payment/opcpay/catalog")
        self.assertEqual(response.json()["data"], payload)
        self.assertEqual(response.json()["code"], 0)
        response = client.post("/api/v1/payment/opcpay/purchase",
            json={"actionId": "test-action", "skuId": "test-sku", "user_id": "8"})
        self.assertEqual(response.status_code, 422)

    def test_remote_error_is_sanitized(self):
        settings = SimpleNamespace(opcpay_api_key=SecretStr("test-secret"))
        transport = httpx.MockTransport(lambda _: httpx.Response(500, json={"error": "test-secret"}))
        with patch("app.modules.payment.opcpay_client.get_settings", return_value=settings):
            with self.assertRaises(AppException) as caught:
                OpcpayClient(transport).access(7)
            self.assertNotIn("test-secret", str(caught.exception))

    def test_timeout_restart_reuses_same_request_and_does_not_expose_staged_text(self):
        self.seed()
        calls = []
        def consume(path, body):
            self.assertEqual(path, "/consume")
            calls.append(body.copy())
            if len(calls) == 1:
                raise AppException(code=3011, message="待确认")
            return success(body)
        with patch("app.modules.task.worker._extract_audio", return_value="audio.wav"), \
             patch("app.modules.task.worker._run_asr", return_value="暂存文稿") as asr, \
             patch.object(OpcpayClient, "request", side_effect=consume):
            process_opcpay_task("TASK-test")
            with self.factory() as db:
                self.assertIsNone(db.scalar(select(Task)).raw_text)
                self.assertEqual(db.scalar(select(OpcpayOperation)).result_text, "暂存文稿")
            self.make_due()
            process_opcpay_task("TASK-test")
            process_opcpay_task("TASK-test")
            self.assertEqual(asr.call_count, 1)
        self.assertEqual(calls, [BODY, BODY])
        with self.factory() as db:
            self.assertEqual(db.scalar(select(Task)).raw_text, "暂存文稿")
            self.assertEqual(db.scalar(select(OpcpayOperation)).state, "DELIVERED")
            self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 1)

    def test_failed_asr_never_consumes(self):
        self.seed()
        with patch("app.modules.task.worker._extract_audio", side_effect=RuntimeError()), \
             patch.object(OpcpayClient, "request") as request:
            process_opcpay_task("TASK-test")
            request.assert_not_called()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(Task)).status, "FAIL")

    def test_duplicate_workers_claim_only_one_lease(self):
        self.seed()
        entered, release = Event(), Event()
        def asr(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test worker timed out")
            return "单次交付"
        with patch("app.modules.task.worker._extract_audio", return_value="audio.wav"), \
             patch("app.modules.task.worker._run_asr", side_effect=asr) as transcribe, \
             patch.object(OpcpayClient, "request", side_effect=lambda path, body: success(body)) as consume:
            worker = Thread(target=process_opcpay_task, args=("TASK-test",))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                process_opcpay_task("TASK-test")
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(transcribe.call_count, 1)
            self.assertEqual(consume.call_count, 1)

    def test_insufficient_balance_rejected_before_task_creation(self):
        from app.modules.quota.service import QuotaService
        with self.factory() as db:
            db.add(UserQuota(user_id=7, remaining_points=0, daily_free_used=0, status="ENABLE"))
            db.commit()
        with self.factory() as db, \
             patch("app.modules.quota.service.get_settings", return_value=SimpleNamespace(opcpay_enabled=True)), \
             patch.object(OpcpayClient, "product", return_value=({}, {"quota_unit": "POINT"})), \
             patch.object(OpcpayClient, "access", return_value={"access_granted": False, "quota_unit": "POINT"}) as access:
            with self.assertRaises(AppException) as caught:
                QuotaService(db).ensure_has_points(7, 10)
            self.assertEqual(caught.exception.code, 2001)
            access.assert_called_once_with(7, 10)

    def test_legacy_balance_remains_usable_without_remote_consumption(self):
        self.seed()
        with self.factory() as db:
            db.add(UserQuota(user_id=7, remaining_points=100, daily_free_used=0, status="ENABLE"))
            op = db.scalar(select(OpcpayOperation))
            op.request_json = json.dumps(json.loads(op.request_json) | {"source": "LOCAL"})
            db.commit()
        with patch("app.modules.task.worker._extract_audio", return_value="audio.wav"), \
             patch("app.modules.task.worker._run_asr", return_value="本地积分文稿"), \
             patch.object(OpcpayClient, "request") as remote:
            process_opcpay_task("TASK-test")
            process_opcpay_task("TASK-test")
            remote.assert_not_called()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 90)
            self.assertEqual(db.scalar(select(Task)).status, "SUCCESS")
            self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 1)

    def test_formal_mode_blocks_mock_callback_before_writes(self):
        from app.modules.payment.service import PaymentService
        from app.modules.payment.schemas import PayNotifyRequest
        with self.factory() as db, patch("app.modules.payment.service.get_settings",
                return_value=SimpleNamespace(opcpay_enabled=True)):
            with self.assertRaises(AppException):
                PaymentService(db).handle_notify(PayNotifyRequest(orderNo="fake", payStatus="SUCCESS"))

    def test_repeated_file_submission_keeps_same_task_and_consumption(self):
        from app.modules.task.service import TaskService
        self.seed()
        with self.factory() as db, patch("app.modules.task.service.get_settings",
                return_value=SimpleNamespace(opcpay_enabled=True)):
            service = TaskService(db)
            file = db.scalar(select(FileRecord))
            first = service.create_task_for_file(7, file)
            second = service.create_task_for_file(7, file)
            self.assertEqual(first.task_no, second.task_no)
            with self.assertRaises(AppException):
                service.create_task_for_file(8, file)

    def test_purchase_duplicate_and_timeout_keep_original_parameters(self):
        cfg = SimpleNamespace(opcpay_enabled=True, opcpay_callback_url="https://example.com/payment", opcpay_trial_sku_id="S0806000214835352")
        calls = []
        def remote(path, body=None):
            calls.append(body.copy())
            if len(calls) == 1:
                raise AppException(code=3011, message="待确认")
            return {"status": "READY", "idempotency_key": body["idempotency_key"], "purchase_url": "https://example.com/pay"}
        with patch("app.modules.payment.opcpay_service.get_settings", return_value=cfg), \
             patch.object(OpcpayService, "catalog", return_value={"plans": [{"skuId": "real-sku", "price": "9.90", "name": "体验包", "quantity": 1000}]}), \
             patch.object(OpcpayClient, "request", side_effect=remote):
            with self.factory() as db:
                with self.assertRaises(AppException):
                    OpcpayService(db).purchase(7, "test-action", "real-sku")
            with self.factory() as db:
                result = OpcpayService(db).purchase(7, "test-action", "real-sku")
                self.assertEqual(OpcpayService(db).purchase(7, "test-action", "real-sku"), result)
                with self.assertRaises(AppException):
                    OpcpayService(db).purchase(7, "test-action", "changed-sku")
                with self.assertRaises(AppException):
                    OpcpayService(db).transaction(8, result["orderNo"])
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(len(calls), 2)

    def test_receipt_and_delivery_rollback_together(self):
        self.seed()
        original_commit = Session.commit
        failed = [False]
        def commit(session):
            if not failed[0] and any(isinstance(o, OpcpayOperation) and o.state == "DELIVERED" for o in session.dirty):
                failed[0] = True
                raise RuntimeError("simulated commit failure")
            return original_commit(session)
        with patch("app.modules.task.worker._extract_audio", return_value="audio.wav"), \
             patch("app.modules.task.worker._run_asr", return_value="文稿") as asr, \
             patch.object(OpcpayClient, "request", side_effect=lambda path, body: success(body)) as consume, \
             patch.object(Session, "commit", commit):
            process_opcpay_task("TASK-test")
            with self.factory() as db:
                self.assertIsNone(db.scalar(select(Task)).raw_text)
                self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 0)
            self.make_due()
            process_opcpay_task("TASK-test")
            self.assertEqual(asr.call_count, 1)
            self.assertEqual(consume.call_count, 2)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(Task)).status, "SUCCESS")
            self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 1)


if __name__ == "__main__":
    unittest.main()
