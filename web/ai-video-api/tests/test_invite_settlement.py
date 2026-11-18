import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import app.models
from app.core.database import Base
from app.core.exceptions import AppException
from app.models.user import User
from app.models.invite import InviteRecord
from app.models.opcpay import OpcpayOperation
from app.models.withdrawal import WithdrawalOrder
from app.modules.invite.settlement import reconcile_purchase
from app.modules.invite.service import InviteService
from app.modules.admin.service import AdminService
from app.modules.admin.schemas import AdminWithdrawalStatusRequest


class InviteSettlementTest(unittest.TestCase):
    def test_first_payment_confirmation_does_not_move_when_polled_again(self):
        first = datetime.now(timezone.utc) - timedelta(days=1)
        reconcile_purchase(self.db, "OP-test", self.observation(when=first))
        first_recorded = json.loads(self.db.scalar(select(OpcpayOperation)).metadata_json)["paid_confirmed_at"]
        reconcile_purchase(self.db, "OP-test", self.observation())
        meta = json.loads(self.db.scalar(select(OpcpayOperation)).metadata_json)
        self.assertEqual(meta["paid_confirmed_at"], first_recorded)
        self.assertNotEqual(meta["paid_confirmed_at"], meta["checked_at"])

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        inviter = User(uid="inviter", email="inviter@example.com", invite_code="INVITER", status="ENABLE")
        self.db.add(inviter)
        self.db.flush()
        invitee = User(uid="invitee", email="invitee@example.com", invite_code="INVITEE", inviter_id=inviter.id, status="ENABLE")
        self.db.add(invitee)
        self.db.flush()
        self.inviter_id, self.invitee_id = inviter.id, invitee.id
        self.db.add(OpcpayOperation(kind="PURCHASE", user_id=invitee.id, biz_no="OP-test", action_id="action-test",
            request_json=json.dumps({"user_id": str(invitee.id), "idempotency_key": "OP-test", "sku_id": "sku-test"}),
            metadata_json=json.dumps({"price": "19.90", "rate": 10, "hold_days": 7, "inviter_id": inviter.id}), state="PENDING"))
        self.db.commit()

    def observation(self, status="PAID", when=None):
        return {"user_id": str(self.invitee_id), "idempotency_key": "OP-test", "status": status,
                "checked_at": (when or datetime.now(timezone.utc)).isoformat(), "status_source": "ALIPAY_PURCHASE_QUERY_V3"}

    def mature(self):
        op = self.db.scalar(select(OpcpayOperation))
        meta = json.loads(op.metadata_json)
        meta["release_at"] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
        op.metadata_json = json.dumps(meta)
        self.db.commit()

    def test_only_verified_payment_creates_one_frozen_reward(self):
        for data in (self.observation() | {"status_source": None}, self.observation() | {"user_id": "other"}, self.observation("UNKNOWN")):
            reconcile_purchase(self.db, "OP-test", data)
        self.assertIsNone(self.db.scalar(select(InviteRecord)))
        reconcile_purchase(self.db, "OP-test", self.observation())
        reconcile_purchase(self.db, "OP-test", self.observation())
        records = list(self.db.scalars(select(InviteRecord)))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].reward_amount, Decimal("1.99"))
        self.assertEqual(records[0].reward_status, "PENDING")
        self.assertEqual(InviteService(self.db).get_withdrawal_summary(self.inviter_id).withdrawableAmount, 0)

    def test_maturity_requires_fresh_observation_and_refund_is_terminal(self):
        reconcile_purchase(self.db, "OP-test", self.observation())
        self.mature()
        reconcile_purchase(self.db, "OP-test", self.observation(when=datetime.now(timezone.utc) - timedelta(days=2)))
        self.assertEqual(self.db.scalar(select(InviteRecord)).reward_status, "PENDING")
        reconcile_purchase(self.db, "OP-test", self.observation())
        self.assertEqual(self.db.scalar(select(InviteRecord)).reward_status, "SUCCESS")
        reconcile_purchase(self.db, "OP-test", self.observation("REFUNDED"))
        reconcile_purchase(self.db, "OP-test", self.observation())
        self.assertEqual(self.db.scalar(select(InviteRecord)).reward_status, "REVERSED")

    def test_withdrawal_reserves_funds_and_cannot_be_paid_after_refund(self):
        op = self.db.scalar(select(OpcpayOperation))
        meta = json.loads(op.metadata_json)
        meta["price"] = "199.00"
        op.metadata_json = json.dumps(meta)
        self.db.commit()
        reconcile_purchase(self.db, "OP-test", self.observation())
        self.mature()
        reconcile_purchase(self.db, "OP-test", self.observation())
        service = InviteService(self.db)
        withdrawal = service.apply_withdrawal(self.inviter_id, "payee@example.com")
        with self.assertRaises(AppException):
            service.apply_withdrawal(self.inviter_id, "payee@example.com")
        self.db.rollback()
        self.assertEqual(len(list(self.db.scalars(select(WithdrawalOrder)))), 1)
        reconcile_purchase(self.db, "OP-test", self.observation("REFUNDED"))
        self.assertEqual(service.get_withdrawal_summary(self.inviter_id).debtAmount, Decimal("19.90"))
        with self.assertRaises(AppException):
            AdminService(self.db).update_withdrawal_status(withdrawal.withdrawNo, AdminWithdrawalStatusRequest(status="PAID"), 999)
        self.db.rollback()
        AdminService(self.db).update_withdrawal_status(withdrawal.withdrawNo, AdminWithdrawalStatusRequest(status="REJECTED"), 999)
        self.assertEqual(service.get_withdrawal_summary(self.inviter_id).debtAmount, 0)
