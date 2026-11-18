"""Opt-in MySQL concurrency tests in a newly-created disposable database, never business tables."""
import json
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from types import SimpleNamespace

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
import app.models
from app.core.config import get_settings
from app.core.database import Base
from app.core.exceptions import AppException
from app.models.user import User
from app.models.invite import InviteRecord
from app.models.opcpay import OpcpayOperation
from app.models.withdrawal import WithdrawalOrder
from app.modules.invite.service import InviteService
from app.modules.invite.settlement import reconcile_purchase


@unittest.skipUnless(os.environ.get("RUN_LOCAL_MYSQL_TESTS") == "1", "opt-in local MySQL only")
class InviteMySQLTest(unittest.TestCase):
    def test_parallel_guest_claims_issue_only_one_device_gift(self):
        from app.core.config import Settings
        from app.modules.guest.service import GuestService
        from app.models.guest import GuestIdentity
        from app.models.quota import UserQuota, QuotaLog
        cfg=Settings(_env_file=None,guest_enabled=True,auth_token_secret="mysql-guest-test")
        barrier=Barrier(2)
        def claim(index):
            with self.factory() as db:
                barrier.wait(timeout=10)
                try:return GuestService(db).claim("same-device-123456789",None,"203.0.113.1")[0]
                except AppException as exc:return exc.code
        with patch("app.modules.guest.service.get_settings",return_value=cfg), ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(claim,range(2)))
        self.assertEqual(results.count(2101),1)
        with self.factory() as db:
            identity=db.scalar(select(GuestIdentity))
            self.assertEqual(db.scalar(select(UserQuota).where(UserQuota.user_id==identity.user_id)).remaining_points,100)
            self.assertEqual(len(list(db.scalars(select(QuotaLog).where(QuotaLog.user_id==identity.user_id)))),1)

    def test_parallel_guest_ip_claim_limit_is_enforced(self):
        from app.core.config import Settings
        from app.modules.guest.service import GuestService
        from app.models.guest import GuestIdentity
        cfg=Settings(_env_file=None,guest_enabled=True,auth_token_secret="mysql-ip-test")
        barrier=Barrier(4)
        def claim(index):
            with self.factory() as db:
                barrier.wait(timeout=10)
                try:GuestService(db).claim("unique-device-"+str(index),None,"203.0.113.2");return True
                except AppException:return False
        with patch("app.modules.guest.service.get_settings",return_value=cfg), ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(claim,range(4)))
        self.assertEqual(sum(results),3)
        with self.factory() as db:self.assertEqual(len(list(db.scalars(select(GuestIdentity)))),3)

    def test_parallel_guest_task_creation_cannot_over_reserve(self):
        from app.core.config import Settings
        from app.models.file import FileRecord
        from app.models.guest import GuestReservation
        from app.modules.guest.service import GuestService
        from app.modules.task.service import TaskService
        cfg=Settings(_env_file=None,guest_enabled=True,opcpay_enabled=True,auth_token_secret="mysql-reserve-test")
        with patch("app.modules.guest.service.get_settings",return_value=cfg), \
             patch("app.modules.task.service.get_settings",return_value=cfg), \
             patch("app.modules.quota.service.get_settings",return_value=cfg):
            with self.factory() as db:
                uid,_=GuestService(db).claim("task-device-123456789",None,"203.0.113.3")
                for i in range(2):db.add(FileRecord(file_no="GFILE-"+str(i),user_id=uid,source_file_name="a.wav",storage_file_name="a.wav",file_type="AUDIO",file_url="a.wav",file_size=1,duration_seconds=360))
                db.commit()
            barrier=Barrier(2)
            def create(index):
                with self.factory() as db:
                    file=db.scalar(select(FileRecord).where(FileRecord.file_no=="GFILE-"+str(index)))
                    barrier.wait(timeout=10)
                    try:
                        TaskService(db).create_task_for_file(uid,file);db.commit();return True
                    except AppException:return False
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(create,range(2)))
            self.assertEqual(sum(results),1)
            with self.factory() as db:self.assertEqual(sum(r.points for r in db.scalars(select(GuestReservation))),60)

    def test_unified_order_projection_and_beijing_daily_totals_on_mysql(self):
        from app.models.payment import PayOrder
        from app.modules.admin.orders import AdminOrderService, CHINA_TZ
        with self.factory() as db:
            db.add(PayOrder(order_no="legacy-order", user_id=self.invitee_id, product_type="POINT_PACK",
                product_name="历史套餐", amount=Decimal("19.90"), status="SUCCESS", paid_at=datetime(2026, 11, 15, 0, 5)))
            db.add(OpcpayOperation(kind="PURCHASE", user_id=self.invitee_id, action_id="new-order", biz_no="new-order",
                request_json="{}", metadata_json=json.dumps({"name":"体验包","price":"9.90","quantity":1000,
                    "payment_status":"PAID","checked_at":"2026-11-14T16:01:00"}),
                response_json=json.dumps({"status":"READY"}), created_at=datetime(2026, 11, 14, 23, 50)))
            db.commit()
            service = AdminOrderService(db)
            self.assertEqual(service.list_orders(None, "PAID", None, 1, 20).total, 2)
            self.assertEqual(service.list_orders("new-order", None, "OPCPAY", 1, 20).records[0].amount, Decimal("9.90"))
            self.assertEqual(service.confirmed_today(datetime(2026, 11, 15, 12, tzinfo=CHINA_TZ)), (2, Decimal("29.80")))
            self.assertEqual(service.successful_count(self.invitee_id), 2)

    def test_parallel_admin_adjustments_preserve_local_balance(self):
        from app.models.quota import UserQuota, QuotaLog
        from app.modules.admin.service import AdminService
        from app.modules.admin.schemas import AdminQuotaAdjustRequest
        with self.factory() as db:
            db.add(UserQuota(user_id=self.invitee_id, remaining_points=84))
            uid = db.get(User, self.invitee_id).uid
            db.commit()
        barrier = Barrier(2)
        def adjust(points):
            with self.factory() as db:
                barrier.wait(timeout=10)
                return AdminService(db).adjust_user_quota(AdminQuotaAdjustRequest(uid=uid, points=points, remark="isolated test"))
        with patch("app.modules.admin.service.get_settings", return_value=SimpleNamespace(opcpay_enabled=True)), \
             patch("app.modules.payment.opcpay_client.OpcpayClient.access", return_value={"quota_unit":"POINT","remaining":1000}), \
             ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(adjust, [10, 20]))
        with self.factory() as db:
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 114)
            self.assertEqual(sum(db.scalars(select(QuotaLog.change_amount))), 30)

    def test_quota_purchase_projection_and_total_on_mysql(self):
        from app.models.quota import UserQuota, QuotaLog
        from app.modules.quota.service import QuotaService
        cfg = SimpleNamespace(opcpay_enabled=True, seconds_per_point=6, init_points=100)
        with self.factory() as db, patch("app.modules.quota.service.get_settings", return_value=cfg), \
             patch("app.modules.payment.opcpay_client.OpcpayClient.access", return_value={"remaining": 1000, "quota_unit": "POINT"}):
            db.add(UserQuota(user_id=self.invitee_id, remaining_points=84))
            db.add(QuotaLog(user_id=self.invitee_id, change_type="REGISTER_GIFT", change_amount=100,
                           before_points=0, after_points=100, biz_no="REGISTER-test"))
            db.add(QuotaLog(user_id=self.invitee_id, change_type="CONSUME", change_amount=-16,
                           before_points=100, after_points=84, biz_no="TASK-test"))
            db.add(OpcpayOperation(kind="PURCHASE", user_id=self.invitee_id, action_id="projection-test", biz_no="OP-projection-test",
                request_json="{}", metadata_json=json.dumps({"quantity": 1000, "name": "体验包", "payment_status": "PAID",
                    "checked_at": "2026-11-15T00:00:00"}), state="PENDING"))
            db.commit()
            service = QuotaService(db)
            info = service.get_quota_info(db.get(User, self.invitee_id))
            self.assertEqual(info.remainingPoints, 1084)
            self.assertEqual(service.list_quota_logs(self.invitee_id, None, 1, 20).total, 3)
            purchased = service.list_quota_logs(self.invitee_id, "PURCHASE", 1, 1)
            self.assertEqual(purchased.records[0].changeAmount, 1000)
            self.assertEqual(service.list_quota_logs(self.inviter_id, "PURCHASE", 1, 20).total, 0)

    def test_parallel_trial_requests_share_one_purchase_intent(self):
        from app.models.opcpay import OpcpayTrialClaim
        from app.modules.payment.opcpay_service import OpcpayService
        from app.modules.payment.opcpay_client import OpcpayClient
        config = SimpleNamespace(opcpay_enabled=True, opcpay_trial_sku_id="trial-sku",
            opcpay_callback_url="https://example.com/payment", invite_reward_hold_days=7)
        catalog={"plans":[{"skuId":"trial-sku","name":"体验包","price":"9.90","quantity":1000}]}
        barrier=Barrier(2)
        def remote(path,body=None):
            return {"status":"READY","idempotency_key":body["idempotency_key"],
                    "purchase_url":"alipays://platformapi/startapp?appId=test"}
        def purchase(index):
            with self.factory() as db:
                barrier.wait(timeout=10)
                return OpcpayService(db).purchase(self.invitee_id,"parallel-action-"+str(index),"trial-sku")["orderNo"]
        with patch("app.modules.payment.opcpay_service.get_settings",return_value=config), \
             patch.object(OpcpayService,"catalog",return_value=catalog), \
             patch.object(OpcpayClient,"request",side_effect=remote), ThreadPoolExecutor(max_workers=2) as pool:
            orders=list(pool.map(purchase,range(2)))
        self.assertEqual(len(set(orders)),1)
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(OpcpayTrialClaim)))),1)
            self.assertEqual(len(list(db.scalars(select(OpcpayOperation).where(OpcpayOperation.kind=="PURCHASE")))),1)

    def test_first_verification_send_is_not_throttled_by_datetime_rounding(self):
        from app.modules.auth.email_codes import EmailCodeService
        from app.models.email_verification import EmailVerification
        with self.factory() as db, patch("app.modules.auth.email_codes.send_verification_email") as send:
            result = EmailCodeService(db).send("mysql-test@example.com", "isolated-mysql-verification")
            self.assertTrue(result["sent"])
            send.assert_called_once()
            self.assertEqual(db.get(EmailVerification, "mysql-test@example.com").state, "READY")
            with self.assertRaises(AppException) as caught:
                EmailCodeService(db).send("mysql-test@example.com", "isolated-mysql-verification")
            self.assertEqual(caught.exception.status_code, 429)

    def setUp(self):
        url = make_url(get_settings().database_url)
        if url.host not in ("localhost", "127.0.0.1", "::1") or not url.drivername.startswith("mysql"):
            self.skipTest("local MySQL required")
        self.schema = "asr_isolated_test_" + secrets.token_hex(8)
        self.control = create_engine(url.set(database=None))
        with self.control.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{self.schema}` CHARACTER SET utf8mb4"))
        self.engine = create_engine(url.set(database=self.schema), isolation_level="REPEATABLE READ")
        self.addCleanup(self.clean)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        with self.factory() as db:
            inviter = User(uid="inviter", email="inviter@example.com", invite_code="INVITER", status="ENABLE")
            db.add(inviter)
            db.flush()
            invitee = User(uid="invitee", email="invitee@example.com", invite_code="INVITEE", inviter_id=inviter.id, status="ENABLE")
            db.add(invitee)
            db.flush()
            self.inviter_id, self.invitee_id = inviter.id, invitee.id
            db.commit()

    def clean(self):
        self.engine.dispose()
        if not self.schema.startswith("asr_isolated_test_") or len(self.schema) != len("asr_isolated_test_") + 16:
            raise RuntimeError("invalid test schema")
        with self.control.begin() as connection:
            connection.execute(text(f"DROP DATABASE `{self.schema}`"))
        self.control.dispose()

    def test_concurrent_withdrawals_cannot_reserve_the_same_money(self):
        with self.factory() as db:
            db.add(InviteRecord(inviter_id=self.inviter_id, invitee_id=self.invitee_id, reward_type="CASH",
                reward_value=0, recharge_amount=Decimal("199.00"), reward_amount=Decimal("19.90"),
                reward_status="SUCCESS", trigger_order_no="OP-test"))
            db.commit()
        barrier = Barrier(2)
        def withdraw():
            with self.factory() as db:
                # Establish a stale RR snapshot, as request authentication can do.
                db.get(User, self.inviter_id)
                barrier.wait(timeout=10)
                try:
                    return InviteService(db).apply_withdrawal(self.inviter_id, "payee@example.com").withdrawNo
                except AppException:
                    db.rollback()
                    return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: withdraw(), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        with self.factory() as db:
            orders = list(db.scalars(select(WithdrawalOrder)))
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0].amount, Decimal("19.90"))

    def test_concurrent_verified_observations_create_only_one_reward(self):
        with self.factory() as db:
            db.add(OpcpayOperation(kind="PURCHASE", user_id=self.invitee_id, action_id="test-action", biz_no="OP-test",
                request_json="{}", state="PENDING", metadata_json=json.dumps({"inviter_id": self.inviter_id,
                    "price": "19.90", "rate": 10, "hold_days": 7})))
            db.commit()
        barrier = Barrier(2)
        data = {"user_id": str(self.invitee_id), "idempotency_key": "OP-test", "status": "PAID",
                "checked_at": datetime.now(timezone.utc).isoformat(), "status_source": "ALIPAY_PURCHASE_QUERY_V3"}
        def reconcile():
            with self.factory() as db:
                db.scalar(select(OpcpayOperation))
                barrier.wait(timeout=10)
                reconcile_purchase(db, "OP-test", data)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: reconcile(), range(2)))
        with self.factory() as db:
            records = list(db.scalars(select(InviteRecord)))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].reward_amount, Decimal("1.99"))
