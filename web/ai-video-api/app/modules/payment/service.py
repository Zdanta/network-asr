import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.payment import PayNotifyLog, PayOrder
from app.modules.invite.service import InviteService
from app.modules.payment.product_policy import ProductPolicyService
from app.modules.payment.schemas import (
    PayNotifyRequest,
    PayNotifyVO,
    PayOrderCreateRequest,
    PayOrderCreateVO,
    PayOrderInfoVO,
)
from app.modules.quota.service import QuotaService
from app.repositories.payment import PayNotifyLogRepository, PayOrderRepository
from app.repositories.system import SysConfigRepository


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.order_repo = PayOrderRepository(db)
        self.notify_repo = PayNotifyLogRepository(db)
        self.product_service = ProductPolicyService(SysConfigRepository(db))
        self.quota_service = QuotaService(db)
        self.invite_service = InviteService(db)

    def create_order(self, user_id: int, request_data: PayOrderCreateRequest) -> PayOrderCreateVO:
        self._ensure_mock_allowed()
        product = self.product_service.get_policy(request_data.productType)
        self._validate_first_purchase(user_id, product.first_purchase_only)
        self._validate_duplicate_order(user_id, product.product_type)

        order = PayOrder(
            order_no=self._generate_order_no(),
            user_id=user_id,
            product_type=product.product_type,
            product_name=product.product_name,
            amount=product.amount,
            pay_channel="MOCK",
            status="INIT",
            notify_status="PENDING",
            third_party_order_no=self._generate_third_party_order_no(),
            remark="模拟订单已创建",
        )
        self.order_repo.add(order)
        self.db.commit()
        return self._to_create_vo(order)

    def get_order(self, user_id: int, order_no: str) -> PayOrderInfoVO:
        order = self.order_repo.get_by_order_no(order_no, user_id=user_id)
        if order is None:
            raise AppException(code=4004, message="订单不存在", status_code=404)
        return self._to_info_vo(order)

    def handle_notify(self, request_data: PayNotifyRequest) -> PayNotifyVO:
        self._ensure_mock_allowed()
        log = self._create_notify_log(request_data)
        try:
            order_no = (request_data.orderNo or "").strip()
            if not order_no:
                raise AppException(code=1001, message="订单号不能为空")
            if request_data.payStatus and request_data.payStatus != "SUCCESS":
                raise AppException(code=3001, message="支付状态不是成功状态")

            order = self.order_repo.get_by_order_no(order_no)
            if order is None:
                raise AppException(code=4004, message="订单不存在", status_code=404)

            if request_data.amount is not None and Decimal(request_data.amount).quantize(Decimal("0.01")) != order.amount:
                raise AppException(code=3002, message="支付金额与订单金额不一致")

            if order.status == "INIT":
                order.status = "SUCCESS"
                order.notify_status = "SUCCESS"
                order.paid_at = datetime.now()
                order.third_party_order_no = request_data.thirdPartyOrderNo or order.third_party_order_no
                order.pay_channel = request_data.payChannel or order.pay_channel
                order.remark = "支付成功"
            elif order.status != "SUCCESS":
                raise AppException(code=3003, message="当前订单状态不允许支付回调")

            self._grant_paid_benefits(order)
            log.notify_status = "SUCCESS"
            log.error_msg = None
            self.db.commit()
            return PayNotifyVO(orderNo=order.order_no, status="SUCCESS")
        except Exception as exc:
            self.db.rollback()
            self._mark_notify_failed(log.id, str(exc))
            raise

    def handle_wechat_notify(self, request_data: PayNotifyRequest) -> PayNotifyVO:
        # TODO: verify WeChat signature and decrypt resource before delegating to handle_notify.
        return self.handle_notify(request_data)

    def _ensure_mock_allowed(self) -> None:
        if get_settings().opcpay_enabled or get_settings().app_env.lower() in {"prod", "production"}:
            raise AppException(code=1003, message="当前环境不支持模拟支付", status_code=403)

    def _grant_paid_benefits(self, order: PayOrder) -> None:
        product = self.product_service.get_policy(order.product_type)
        self.quota_service.add_quota_once(
            user_id=order.user_id,
            points=product.points,
            biz_no=order.order_no,
            change_type="PURCHASE",
            remark="购买额度到账",
        )
        self.invite_service.handle_paid_reward(order)

    def _create_notify_log(self, request_data: PayNotifyRequest) -> PayNotifyLog:
        notify_body = request_data.notifyBody or json.dumps(request_data.model_dump(mode="json"), ensure_ascii=False)
        log = PayNotifyLog(
            order_no=request_data.orderNo,
            third_party_order_no=request_data.thirdPartyOrderNo,
            pay_channel=request_data.payChannel or "MOCK",
            notify_body=notify_body,
            notify_status="RECEIVED",
        )
        self.notify_repo.add(log)
        self.db.commit()
        return log

    def _mark_notify_failed(self, log_id: int, error_msg: str) -> None:
        log = self.notify_repo.get(log_id)
        if log is not None:
            log.notify_status = "FAIL"
            log.error_msg = error_msg[:1000]
            self.db.commit()

    def _validate_first_purchase(self, user_id: int, first_purchase_only: bool) -> None:
        if first_purchase_only and self.order_repo.count_success_orders(user_id) > 0:
            raise AppException(code=3004, message="首充礼包仅限首次支付前购买")

    def _validate_duplicate_order(self, user_id: int, product_type: str) -> None:
        since = datetime.now() - timedelta(seconds=max(1, get_settings().payment_duplicate_order_window_seconds))
        if self.order_repo.get_recent_init_order(user_id, product_type, since) is not None:
            raise AppException(code=3005, message="已有待支付订单，请先完成或稍后再试")

    def _generate_order_no(self) -> str:
        for _ in range(10):
            order_no = f"ORDER{secrets.token_hex(8).upper()}"
            if self.order_repo.get_by_order_no(order_no) is None:
                return order_no
        raise AppException(code=5000, message="订单号生成失败，请稍后重试", status_code=500)

    def _generate_third_party_order_no(self) -> str:
        return f"MOCK{secrets.token_hex(8).upper()}"

    def _to_create_vo(self, order: PayOrder) -> PayOrderCreateVO:
        pay_url = f"{get_settings().mock_pay_url_prefix}{order.order_no}"
        return PayOrderCreateVO(
            orderNo=order.order_no,
            productType=order.product_type,
            productName=order.product_name,
            amount=order.amount,
            status=order.status,
            payUrl=pay_url,
            qrCode=pay_url,
        )

    def _to_info_vo(self, order: PayOrder) -> PayOrderInfoVO:
        return PayOrderInfoVO(
            orderNo=order.order_no,
            productType=order.product_type,
            amount=order.amount,
            status=order.status,
            paidAt=order.paid_at,
        )
