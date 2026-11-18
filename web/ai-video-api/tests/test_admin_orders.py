import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.core.exceptions import AppException, register_exception_handlers
from app.models.user import User
from app.models.opcpay import OpcpayOperation
from app.models.payment import PayOrder
from app.modules.admin.orders import AdminOrderService, CHINA_TZ


class AdminOrdersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name) / "orders.db"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as db:
            db.add_all([User(id=7, uid="buyer-seven", email="seven@example.com", invite_code="SEVEN"),
                        User(id=8, uid="buyer-eight", email="eight@example.com", invite_code="EIGHT")])
            db.add(PayOrder(order_no="legacy-paid", user_id=8, product_type="POINT_PACK", product_name="旧套餐",
                            amount=Decimal("19.90"), status="SUCCESS", paid_at=datetime(2026, 11, 15, 0, 3)))
            db.add(PayOrder(order_no="legacy-pending", user_id=8, product_type="POINT_PACK", product_name="旧套餐",
                            amount=Decimal("8.00"), status="INIT"))
            for biz, status, checked, first in [
                ("provider-paid", "PAID", "2026-11-14T16:01:00", None),
                ("provider-yesterday", "PAID", "2026-11-14T15:59:59", None),
                ("provider-refunded", "REFUNDED", "2026-11-14T16:02:00", None),
                ("provider-pending", "UNKNOWN", None, None),
                ("provider-unchecked", "PAID", None, None),
                ("provider-rechecked", "PAID", "2026-11-14T16:03:00", "2026-11-13T16:00:00")]:
                meta = {"name": "体验包", "price": "9.90", "quantity": 1000, "payment_status": status}
                if checked:
                    meta["checked_at"] = checked
                if first:
                    meta["paid_confirmed_at"] = first
                db.add(OpcpayOperation(kind="PURCHASE", user_id=7, action_id=biz, biz_no=biz, request_json="{}",
                    metadata_json=json.dumps(meta), response_json=json.dumps({"status": "READY"}),
                    created_at=datetime(2026, 11, 14, 23, 50)))
            db.commit()

    def test_all_orders_search_filter_pagination_and_read_only(self):
        with Session(self.engine) as db:
            service = AdminOrderService(db)
            count = db.scalar(select(func.count()).select_from(OpcpayOperation))
            self.assertEqual(service.list_orders(None, None, None, 1, 20).total, 8)
            pages = [service.list_orders(None, None, None, page, 3) for page in (1, 2, 3)]
            self.assertEqual([len(p.records) for p in pages], [3, 3, 2])
            self.assertEqual(len({(r.source, r.orderNo) for p in pages for r in p.records}), 8)
            self.assertEqual(service.list_orders(None, "PAID", None, 1, 20).total, 4)
            self.assertEqual(service.list_orders(None, "PENDING", None, 1, 20).total, 2)
            self.assertEqual(service.list_orders(None, "UNKNOWN", None, 1, 20).total, 1)
            self.assertEqual(service.list_orders(None, None, "LEGACY", 1, 20).total, 2)
            self.assertEqual(service.list_orders("seven@example.com", None, None, 1, 20).total, 6)
            self.assertEqual(service.list_orders("provider-paid", None, None, 1, 20).total, 1)
            self.assertEqual(service.successful_count(7), 3)
            self.assertEqual(db.scalar(select(func.count()).select_from(OpcpayOperation)), count)
            with self.assertRaises(AppException):
                service.list_orders(None, "SUCCESS", None, 1, 20)
            with self.assertRaises(AppException):
                service.list_orders(None, None, "bad", 1, 20)

    def test_today_uses_beijing_first_confirmation_not_order_creation_or_recheck(self):
        with Session(self.engine) as db:
            service = AdminOrderService(db)
            count, amount = service.confirmed_today(datetime(2026, 11, 15, 12, tzinfo=CHINA_TZ))
            self.assertEqual(count, 2)
            self.assertEqual(amount, Decimal("29.80"))
            row = service.list_orders("provider-paid", None, None, 1, 20).records[0]
            self.assertEqual(row.paymentConfirmedAt.isoformat(), "2026-11-15T00:01:00+08:00")
            self.assertEqual(row.createdAt.day, 14)
            self.assertNotIn("request_json", row.model_dump())

    def test_verified_provider_record_deduplicates_legacy_and_refund_is_not_paid(self):
        with Session(self.engine) as db:
            db.add(PayOrder(order_no="provider-paid", user_id=7, product_type="POINT_PACK", product_name="duplicate",
                            amount=Decimal("9.90"), status="SUCCESS", paid_at=datetime(2026, 11, 15, 0, 1)))
            db.add(PayOrder(order_no="provider-refunded", user_id=7, product_type="POINT_PACK", product_name="duplicate",
                            amount=Decimal("9.90"), status="SUCCESS", paid_at=datetime(2026, 11, 15, 0, 2)))
            db.commit()
            service = AdminOrderService(db)
            self.assertEqual(service.list_orders(None, None, None, 1, 20).total, 8)
            self.assertEqual(service.confirmed_today(datetime(2026, 11, 15, 12, tzinfo=CHINA_TZ)), (2, Decimal("29.80")))

    def test_orders_http_requires_admin_and_valid_pagination(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from app.core.security import CurrentUser, get_current_user
        from app.modules.admin.router import router
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1/admin")
        def db_override():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = db_override
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/admin/orders").status_code, 401)
            app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7, uid="buyer-seven", mobile=None, is_admin=False)
            self.assertEqual(client.get("/api/v1/admin/orders").status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7, uid="buyer-seven", mobile=None, is_admin=True)
            response = client.get("/api/v1/admin/orders?status=PAID&pageSize=2")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["total"], 4)
            self.assertEqual(client.get("/api/v1/admin/orders?pageNo=0").status_code, 422)

