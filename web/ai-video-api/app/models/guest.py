from app.common.clock import utc_naive_now
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.base import IdMixin


class GuestIdentity(Base):
    __tablename__ = "guest_identity"
    __table_args__ = (Index("idx_guest_created", "created_at"), Index("idx_guest_expiry", "state", "expires_at"))
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="GUEST", nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger)
    initial_points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_naive_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime)
    upload_lease: Mapped[str | None] = mapped_column(String(36))
    upload_until: Mapped[datetime | None] = mapped_column(DateTime)


class GuestLimitLock(Base):
    __tablename__ = "guest_limit_lock"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)


class GuestReservation(Base):
    __tablename__ = "guest_reservation"
    __table_args__ = (Index("idx_guest_res_window", "state", "created_at"),)
    task_no: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="RESERVED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_naive_now, nullable=False)


class GuestEvent(IdMixin, Base):
    __tablename__ = "guest_event"
    __table_args__ = (Index("idx_guest_event_limits", "ip_hash", "created_at"),)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
