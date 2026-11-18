from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class PayOrder(IdMixin, Base):
    __tablename__ = "pay_order"
    __table_args__ = (
        UniqueConstraint("order_no", name="uk_pay_order_order_no"),
        Index("idx_pay_order_user_id", "user_id"),
        Index("idx_pay_order_status", "status"),
        Index("idx_pay_order_product_type", "product_type"),
        Index("idx_pay_order_paid_at", "paid_at"),
        Index("idx_pay_order_third_party_order_no", "third_party_order_no"),
    )

    order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    product_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    pay_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="WECHAT_NATIVE", server_default="WECHAT_NATIVE")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="INIT", server_default="INIT")
    third_party_order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notify_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PayNotifyLog(IdMixin, Base):
    __tablename__ = "pay_notify_log"
    __table_args__ = (
        Index("idx_pay_notify_log_order_no", "order_no"),
        Index("idx_pay_notify_log_third_party_order_no", "third_party_order_no"),
        Index("idx_pay_notify_log_notify_status", "notify_status"),
        Index("idx_pay_notify_log_created_at", "created_at"),
    )

    order_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    third_party_order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pay_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="WECHAT_NATIVE", server_default="WECHAT_NATIVE")
    notify_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    notify_status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED", server_default="RECEIVED")
    error_msg: Mapped[str | None] = mapped_column(String(1000), nullable=True)
