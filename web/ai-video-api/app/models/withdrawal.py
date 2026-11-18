from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class WithdrawalOrder(IdMixin, Base):
    __tablename__ = "withdrawal_order"
    __table_args__ = (
        UniqueConstraint("withdraw_no", name="uk_withdrawal_order_no"),
        Index("idx_withdrawal_order_user_id", "user_id"),
        Index("idx_withdrawal_order_status", "status"),
        Index("idx_withdrawal_order_created_at", "created_at"),
        Index("idx_withdrawal_order_user_status", "user_id", "status"),
    )

    withdraw_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    alipay_account: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    handled_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
