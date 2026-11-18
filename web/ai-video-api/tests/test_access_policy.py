from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import app.models
from app.core.database import Base
from app.core.exceptions import AppException
from app.core import security
from app.models.user import User
from app.models.opcpay import OpcpayOperation, OpcpayTrialClaim
from app.modules.payment.opcpay_service import OpcpayService
from app.modules.payment.opcpay_client import OpcpayClient
from app.modules.invite.settlement import reconcile_purchase


class AccessPolicyTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.settings = SimpleNamespace(opcpay_enabled=True, opcpay_trial_sku_id="trial-sku",
            opcpay_callback_url="https://example.com/payment", invite_reward_hold_days=7,
            auth_token_secret="test-only-secret", auth_token_expire_seconds=0,
            admin_email_whitelist="1713674324@qq.com", admin_mobiles=set())

    def test_tokens_do_not_expire_but_logout_survives_process_restart(self):
        with patch.object(security, "get_settings", return_value=self.settings):
            with patch.object(security.time, "time", return_value=1000):
                token = security.create_access_token(7)
            with patch.object(security.time, "time", return_value=1000 + 60*60*24*365*100):
                with self.factory() as db:
                    self.assertEqual(security.parse_access_token(token, db), 7)
                    security.revoke_access_token(token, db)
                security._REVOKED_TOKENS.clear()  # simulate restart/new API process
                with self.factory() as db, self.assertRaises(AppException):
                    security.parse_access_token(token, db)

    def test_expiry_still_works_when_explicitly_configured(self):
        self.settings.auth_token_expire_seconds = 60
        with patch.object(security, "get_settings", return_value=self.settings):
            with patch.object(security.time, "time", return_value=1000):
                token = security.create_access_token(7)
            with patch.object(security.time, "time", return_value=1061), self.assertRaises(AppException):
                security.parse_access_token(token)

    def test_requested_email_is_admin(self):
        with patch.object(security, "get_settings", return_value=self.settings):
            self.assertTrue(security.is_admin_user(User(email="1713674324@qq.com")))
            self.assertFalse(security.is_admin_user(User(email="someone@example.com")))

    def test_trial_once_and_readonly_recovery_support_alipays_and_qr(self):
        with self.factory() as db:
            user = User(uid="user-7", email="trial@example.com", invite_code="TRIAL", status="ENABLE")
            db.add(user)
            db.commit()
            user_id = user.id
            plans = {"enabled": True, "plans": [{"skuId":"trial-sku","price":"9.90","name":"体验包","quantity":1000}]}
            def remote(path, body=None):
                self.assertEqual(path, "/purchase")
                return {"status":"READY", "idempotency_key":body["idempotency_key"],
                    "purchase_url":"alipays://platformapi/startapp?appId=test",
                    "purchase_qr_code":"https://mobilecodec.alipay.com/show.htm?code=test"}
            with patch("app.modules.payment.opcpay_service.get_settings", return_value=self.settings), \
                 patch.object(OpcpayService, "catalog", return_value=plans), \
                 patch.object(OpcpayClient, "request", side_effect=remote) as request:
                first = OpcpayService(db).purchase(user_id,"action-first","trial-sku")
                again = OpcpayService(db).purchase(user_id,"action-second","trial-sku")
                self.assertEqual(first, again)
                self.assertEqual(request.call_count, 1)
                restored = OpcpayService(db).entry(user_id, first["orderNo"])
                self.assertTrue(restored["payUrl"].startswith("alipays://"))
                self.assertTrue(restored["qrCode"].startswith("https://"))
                with self.assertRaises(AppException):
                    OpcpayService(db).entry(user_id + 1,first["orderNo"])
            now = datetime.now(timezone.utc).isoformat()
            observation={"status":"PAID","checked_at":now,"status_source":"ALIPAY_PURCHASE_QUERY_V3",
                         "user_id":str(user_id),"idempotency_key":first["orderNo"]}
            reconcile_purchase(db,first["orderNo"],observation)
            self.assertIsNotNone(db.get(OpcpayTrialClaim,user_id).paid_at)
            caps={"capabilities":{"transaction_query":True}}
            product={"billing_mode":"QUANTITY","quota_unit":"POINT","charging_options":[
                {"sku_id":"trial-sku","price":"9.90","display_name":"体验包","quota_amount":1000},
                {"sku_id":"regular","price":"19.90","display_name":"日常包","quota_amount":1100}]}
            with patch("app.modules.payment.opcpay_service.get_settings", return_value=self.settings), \
                 patch.object(OpcpayClient, "product", return_value=(caps,product)):
                self.assertEqual([p["skuId"] for p in OpcpayService(db).catalog(user_id)["plans"]],["regular"])
                for action in ["action-first","brand-new-action"]:
                    with self.assertRaises(AppException) as caught:
                        OpcpayService(db).purchase(user_id,action,"trial-sku")
                    self.assertEqual(caught.exception.code,3013)
            observation["status"]="REFUNDED"
            reconcile_purchase(db,first["orderNo"],observation)
            self.assertIsNotNone(db.get(OpcpayTrialClaim,user_id).paid_at)
