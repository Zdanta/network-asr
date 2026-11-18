import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.core.exceptions import AppException
from app.models.user import User
from app.models.quota import UserQuota, QuotaLog
from app.models.payment import PayOrder
from app.models.opcpay import OpcpayOperation
from app.modules.admin.service import AdminService
from app.modules.admin.schemas import AdminQuotaAdjustRequest


class AdminQuotaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "admin.db"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        cfg = SimpleNamespace(opcpay_enabled=True)
        settings = patch("app.modules.admin.service.get_settings", return_value=cfg)
        settings.start()
        self.addCleanup(settings.stop)
        with Session(self.engine) as db:
            db.add_all([User(id=7, uid="seven", email="seven@example.com", invite_code="SEVEN"),
                        User(id=8, uid="eight", email="eight@example.com", invite_code="EIGHT")])
            db.add(UserQuota(user_id=7, remaining_points=84))
            for biz, status, checked in [("paid", "PAID", True), ("pending", "UNKNOWN", False),
                                         ("unchecked", "PAID", False), ("refund", "REFUNDED", True)]:
                meta = {"payment_status": status}
                if checked:
                    meta["checked_at"] = "2026-11-15T00:00:00"
                db.add(OpcpayOperation(kind="PURCHASE", user_id=7, action_id=biz, biz_no=biz,
                                      request_json="{}", metadata_json=json.dumps(meta)))
            db.commit()

    def test_list_and_detail_include_provider_balance_and_verified_payment_count(self):
        with Session(self.engine) as db, patch("app.modules.payment.opcpay_client.OpcpayClient.access",
                side_effect=lambda uid: {"quota_unit": "POINT", "remaining": 1000 if uid == 7 else 0}):
            service = AdminService(db)
            page = service.list_users(None, 1, 20)
            user = next(r for r in page.records if r.uid == "seven")
            detail = service.get_user_detail("seven")
            for row in (user, detail):
                self.assertEqual((row.remainingPoints, row.localRemainingPoints, row.purchasedRemainingPoints), (1084, 84, 1000))
                self.assertEqual(row.paidOrderCount, 1)
            self.assertEqual(next(r for r in page.records if r.uid == "eight").remainingPoints, 0)
            self.assertEqual(service.list_users("seven@example.com", 1, 1).total, 1)
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 84)

    def test_verified_payment_count_deduplicates_legacy_order(self):
        with Session(self.engine) as db:
            db.add(PayOrder(order_no="paid", user_id=7, product_type="POINT_PACK", product_name="test", amount=9.9, status="SUCCESS"))
            db.commit()
            self.assertEqual(AdminService(db)._successful_order_count(7), 1)

    def test_provider_failure_is_not_reported_as_local_only_total(self):
        with Session(self.engine) as db, patch("app.modules.payment.opcpay_client.OpcpayClient.access",
                side_effect=AppException(code=3011, message="待确认")):
            with self.assertRaises(AppException):
                AdminService(db).list_users(None, 1, 20)
            with self.assertRaises(AppException):
                AdminService(db).adjust_user_quota(AdminQuotaAdjustRequest(uid="seven", points=10, remark="test"))
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 84)
            self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 0)

    def test_adjust_updates_only_local_wallet_and_returns_total(self):
        with Session(self.engine) as db, patch("app.modules.payment.opcpay_client.OpcpayClient.access",
                return_value={"quota_unit": "POINT", "remaining": 1000}) as access:
            detail = AdminService(db).adjust_user_quota(AdminQuotaAdjustRequest(uid="seven", points=10, remark="test"))
            self.assertEqual((detail.remainingPoints, detail.localRemainingPoints, detail.purchasedRemainingPoints), (1094, 94, 1000))
            access.assert_called_once_with(7)
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 94)
            self.assertEqual(db.scalar(select(QuotaLog)).change_amount, 10)


if __name__ == "__main__":
    unittest.main()
