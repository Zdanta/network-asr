import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.models.opcpay import OpcpayOperation
from app.models.quota import QuotaLog, UserQuota
from app.modules.quota.service import QuotaService


class QuotaSummaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "quota.db"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        cfg = SimpleNamespace(opcpay_enabled=True, seconds_per_point=6, init_points=100)
        settings = patch("app.modules.quota.service.get_settings", return_value=cfg)
        settings.start()
        self.addCleanup(settings.stop)
        with Session(self.engine) as db:
            db.add(UserQuota(user_id=7, remaining_points=100))
            db.add(QuotaLog(user_id=7, change_type="REGISTER_GIFT", change_amount=100,
                           before_points=0, after_points=100, biz_no="REGISTER-7"))
            db.commit()

    def purchase(self, db, biz, status="PAID", user=7, quantity=1000, checked=True):
        meta = {"quantity": quantity, "name": "体验包", "payment_status": status}
        if checked:
            meta["checked_at"] = "2026-11-15T00:00:00"
        db.add(OpcpayOperation(kind="PURCHASE", user_id=user, action_id=biz, biz_no=biz,
                              request_json="{}", metadata_json=json.dumps(meta), state="PENDING"))
        db.commit()

    def test_total_preserves_gift_and_local_debits_without_crediting_purchase_twice(self):
        user = SimpleNamespace(id=7, vip_expire_time=None)
        with Session(self.engine) as db, patch("app.modules.payment.opcpay_client.OpcpayClient.access",
                return_value={"remaining": 1000, "quota_unit": "POINT"}):
            service = QuotaService(db)
            self.assertEqual(service.get_quota_info(user).remainingPoints, 1100)
            service.consume_points_once(7, 16, "TASK-16", "原有额度扣除")
            db.commit()
            quota = service.get_quota_info(user)
            self.assertEqual((quota.remainingPoints, quota.localRemainingPoints, quota.purchasedRemainingPoints), (1084, 84, 1000))
            self.purchase(db, "OP-paid")
            for _ in range(2):
                ledger = service.list_quota_logs(7, None, 1, 20)
                self.assertEqual(sum(r.changeAmount for r in ledger.records), 1084)
            self.assertEqual(db.scalar(select(UserQuota)).remaining_points, 84)
            self.assertEqual(len(list(db.scalars(select(QuotaLog)))), 2)

    def test_verified_purchases_merge_with_filters_pagination_and_ownership(self):
        with Session(self.engine) as db:
            self.purchase(db, "paid")
            self.purchase(db, "pending", "UNKNOWN")
            self.purchase(db, "ready", "READY")
            self.purchase(db, "unchecked", checked=False)
            self.purchase(db, "other-user", user=8)
            service = QuotaService(db)
            purchases = service.list_quota_logs(7, "PURCHASE", 1, 20)
            self.assertEqual([r.bizNo for r in purchases.records], ["paid"])
            self.assertIsNone(purchases.records[0].afterPoints)
            all_rows = service.list_quota_logs(7, "ALL", 1, 20)
            self.assertEqual(all_rows.total, 2)
            first = service.list_quota_logs(7, None, 1, 1)
            second = service.list_quota_logs(7, None, 2, 1)
            self.assertEqual(first.pages, 2)
            self.assertNotEqual(first.records[0].bizNo, second.records[0].bizNo)
            self.assertEqual(service.list_quota_logs(7, "REGISTER_GIFT", 1, 20).total, 1)
            self.assertEqual(service.list_quota_logs(7, "CONSUME", 1, 20).total, 0)

    def test_refund_is_labelled_and_existing_purchase_log_not_duplicated(self):
        with Session(self.engine) as db:
            self.purchase(db, "refund", "REFUNDED")
            self.purchase(db, "recorded")
            db.add(QuotaLog(user_id=7, change_type="PURCHASE", change_amount=1000,
                           before_points=0, after_points=1000, biz_no="recorded"))
            db.commit()
            rows = QuotaService(db).list_quota_logs(7, "PURCHASE", 1, 20)
            self.assertEqual(rows.total, 2)
            self.assertIn("已退款", next(r.remark for r in rows.records if r.bizNo == "refund"))


if __name__ == "__main__":
    unittest.main()
