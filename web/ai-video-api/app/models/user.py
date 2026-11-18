from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import quoted_name

from app.core.database import Base
from app.models.base import IdMixin


class User(IdMixin, Base):
    __tablename__ = quoted_name("user", True)
    __table_args__ = (
        UniqueConstraint("uid", name="uk_user_uid"),
        UniqueConstraint("invite_code", name="uk_user_invite_code"),
        UniqueConstraint("mobile", name="uk_user_mobile"),
        UniqueConstraint("email", name="uk_user_email"),
        Index("idx_user_inviter_id", "inviter_id"),
        Index("idx_user_status", "status"),
        Index("idx_user_vip_expire_time", "vip_expire_time"),
    )

    uid: Mapped[str] = mapped_column(String(36), nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invite_code: Mapped[str] = mapped_column(String(32), nullable=False)
    inviter_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vip_expire_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLE", server_default="ENABLE")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UserLoginLog(IdMixin, Base):
    __tablename__ = "user_login_log"
    __table_args__ = (
        Index("idx_user_login_log_user_id", "user_id"),
        Index("idx_user_login_log_status", "status"),
        Index("idx_user_login_log_created_at", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    login_type: Mapped[str] = mapped_column(String(32), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCESS", server_default="SUCCESS")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
