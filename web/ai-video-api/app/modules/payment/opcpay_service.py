import json
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.opcpay import OpcpayOperation, OpcpayTrialClaim
from app.modules.payment.opcpay_client import OpcpayClient


class OpcpayService:
    def __init__(self, db):
        self.db = db
        self.client = OpcpayClient()

    def catalog(self, user_id: int | None = None):
        if not get_settings().opcpay_enabled:
            return {"enabled": False, "plans": []}
        caps, product = self.client.product()
        claim = self.db.get(OpcpayTrialClaim, user_id) if user_id is not None else None
        trial_used = bool(claim and claim.paid_at)
        return {"enabled": True, "billingMode": product["billing_mode"], "quotaUnit": product["quota_unit"],
                "transactionQuery": caps["capabilities"].get("transaction_query") is True,
                "plans": [{"skuId": p["sku_id"], "name": p.get("display_name", "积分包"),
                           "price": p["price"], "quantity": p.get("quota_amount", 0)}
                          for p in product.get("charging_options", [])
                          if not (trial_used and p["sku_id"] == get_settings().opcpay_trial_sku_id)]}

    def require_enabled(self):
        if not get_settings().opcpay_enabled:
            raise AppException(code=3012, message="一人付尚未启用", status_code=503)

    def purchase(self, user_id: int, action_id: str, sku_id: str):
        self.require_enabled()
        is_trial = sku_id == get_settings().opcpay_trial_sku_id
        # Resolve the existing intent BEFORE consulting a possibly changed catalog.
        op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE",
            OpcpayOperation.user_id == user_id, OpcpayOperation.action_id == action_id))
        if is_trial:
            claim = self.db.scalar(select(OpcpayTrialClaim).where(OpcpayTrialClaim.user_id == user_id).with_for_update())
            if claim and claim.paid_at:
                raise AppException(code=3013, message="体验包仅限购买一次，已购买后不可再次开通")
            if claim and op is None:
                op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.biz_no == claim.order_no,
                    OpcpayOperation.user_id == user_id))
            if op and json.loads(op.metadata_json or "{}").get("payment_status") in {"PAID", "REFUNDED"}:
                raise AppException(code=3013, message="体验包仅限购买一次，已购买后不可再次开通")
        if op is None:
            self.db.commit()
            catalog = self.catalog()
            if sku_id not in {p["skuId"] for p in catalog["plans"]}:
                raise AppException(code=1001, message="套餐不存在或已下架")
            from app.models.user import User
            from app.modules.invite.service import InviteService
            account = self.db.scalar(select(User).where(User.id == user_id).with_for_update()) if is_trial else self.db.get(User, user_id)
            if is_trial:
                claim = self.db.scalar(select(OpcpayTrialClaim).where(OpcpayTrialClaim.user_id == user_id)
                                       .with_for_update().execution_options(populate_existing=True))
                if claim:
                    if claim.paid_at:
                        raise AppException(code=3013, message="体验包仅限购买一次，已购买后不可再次开通")
                    original = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.biz_no == claim.order_no))
                    self.db.commit()
                    if original is None:
                        raise AppException(code=3011, message="原体验包记录待核实，请联系管理员")
                    return self.purchase(user_id, original.action_id, sku_id)
            selected = next(p for p in catalog["plans"] if p["skuId"] == sku_id)
            snapshot = {"price": str(selected["price"]), "name": selected["name"], "quantity": selected["quantity"],
                        "inviter_id": account.inviter_id if account else None,
                        "rate": InviteService(self.db)._invite_reward_rate_percent(),
                        "hold_days": getattr(get_settings(), "invite_reward_hold_days", 7),
                        "payment_status": "UNKNOWN"}
            biz_no = "OP" + uuid.uuid4().hex
            body = {"user_id": str(user_id), "idempotency_key": biz_no, "sku_id": sku_id}
            callback = get_settings().opcpay_callback_url
            if callback:
                parsed = urlsplit(callback)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or len(callback.encode()) > 512:
                    raise AppException(code=3012, message="支付返回地址配置不正确，请联系管理员", status_code=503)
                body["callback_url"] = callback
            op = OpcpayOperation(kind="PURCHASE", user_id=user_id, action_id=action_id,
                                 biz_no=biz_no, request_json=json.dumps(body), metadata_json=json.dumps(snapshot), state="PENDING")
            self.db.add(op)
            if is_trial:
                self.db.add(OpcpayTrialClaim(user_id=user_id, sku_id=sku_id, order_no=biz_no))
            try:
                self.db.commit()  # Intent durable before any remote write.
            except IntegrityError:
                self.db.rollback()
                op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE",
                    OpcpayOperation.user_id == user_id, OpcpayOperation.action_id == action_id))
                if op is None:
                    if is_trial:
                        claim = self.db.get(OpcpayTrialClaim, user_id)
                        original = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.biz_no == claim.order_no)) if claim else None
                        if original:
                            return self.purchase(user_id, original.action_id, sku_id)
                    raise
        body = json.loads(op.request_json)
        if body["sku_id"] != sku_id:
            raise AppException(code=1001, message="同一购买编号不能更换套餐")
        data = json.loads(op.response_json) if op.response_json else {}
        if data.get("status") != "READY":
            self.db.commit()  # No transaction is held while waiting on provider.
            data = self.client.request("/purchase", body)
            if data.get("idempotency_key") != op.biz_no:
                raise AppException(code=3011, message="购买结果待核实，请使用原编号重试", status_code=503)
            op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.id == op.id).with_for_update()
                                .execution_options(populate_existing=True))
            op.response_json = json.dumps(data)
            # Prefer the locked SKU price when the provider supplies it.
            option = data.get("charging_option", {})
            if op.metadata_json and option.get("sku_id") == body["sku_id"] and option.get("currency") == "CNY":
                from decimal import Decimal
                try:
                    price = Decimal(str(option["price"]))
                    if price.is_finite() and price > 0:
                        snapshot = json.loads(op.metadata_json)
                        snapshot["price"] = str(price)
                        op.metadata_json = json.dumps(snapshot)
                except (KeyError, ValueError, ArithmeticError):
                    pass
            self.db.commit()
        return self._entry_vo(op)

    def entry(self, user_id: int, biz_no: str):
        self.require_enabled()
        op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE",
            OpcpayOperation.user_id == user_id, OpcpayOperation.biz_no == biz_no))
        if op is None:
            raise AppException(code=4004, message="购买记录不存在", status_code=404)
        return self._entry_vo(op)

    @staticmethod
    def _entry_vo(op):
        data = json.loads(op.response_json or "{}")
        return {"orderNo": op.biz_no, "status": data.get("status", "UNKNOWN"),
                "payUrl": data.get("purchase_url") if data.get("status") == "READY" else None,
                "qrCode": data.get("purchase_qr_code") if data.get("status") == "READY" else None,
                "expiresAt": data.get("expire_time")}

    def transaction(self, user_id: int, biz_no: str):
        self.require_enabled()
        op = self.db.scalar(select(OpcpayOperation).where(OpcpayOperation.kind == "PURCHASE",
            OpcpayOperation.user_id == user_id, OpcpayOperation.biz_no == biz_no))
        if op is None:
            raise AppException(code=4004, message="订单不存在", status_code=404)
        self.db.commit()
        caps = self.client.request("/capabilities")
        if caps.get("capabilities", {}).get("transaction_query") is not True:
            return {"status": "UNKNOWN", "checkedAt": None}
        data = self.client.request("/transactions/query", {"user_id": str(user_id), "idempotency_key": op.biz_no})
        if data.get("user_id") != str(user_id) or data.get("idempotency_key") != op.biz_no:
            return {"status": "UNKNOWN", "checkedAt": None}
        if data.get("status") in {"PAID", "REFUNDED"} and (
                data.get("status_source") != "ALIPAY_PURCHASE_QUERY_V3" or not data.get("checked_at")):
            return {"status": "UNKNOWN", "checkedAt": None}
        from app.modules.invite.settlement import reconcile_purchase
        reconcile_purchase(self.db, op.biz_no, data)
        return {"status": data.get("status", "UNKNOWN"), "checkedAt": data.get("checked_at")}
