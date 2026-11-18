from decimal import Decimal

from sqlalchemy import BigInteger, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class InviteRecord(IdMixin, Base):
    __tablename__ = "invite_record"
    __table_args__ = (
        UniqueConstraint("trigger_order_no", name="uk_invite_record_trigger_order_no"),
        Index("idx_invite_record_inviter_id", "inviter_id"),
        Index("idx_invite_record_reward_status", "reward_status"),
        Index("idx_invite_record_invitee_id", "invitee_id"),
    )

    inviter_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invitee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reward_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reward_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    recharge_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    reward_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    trigger_order_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
