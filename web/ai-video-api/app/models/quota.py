from datetime import date

from sqlalchemy import BigInteger, Date, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class UserQuota(IdMixin, Base):
    __tablename__ = "user_quota"
    __table_args__ = (
        UniqueConstraint("user_id", name="uk_user_quota_user_id"),
        Index("idx_user_quota_status", "status"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining_points: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    daily_free_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLE", server_default="ENABLE")


class QuotaLog(IdMixin, Base):
    __tablename__ = "quota_log"
    __table_args__ = (
        Index("idx_quota_log_user_id", "user_id"),
        Index("idx_quota_log_change_type", "change_type"),
        Index("idx_quota_log_biz_no", "biz_no"),
        Index("idx_quota_log_created_at", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    change_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    before_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    after_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    biz_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
