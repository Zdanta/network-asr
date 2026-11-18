from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class Message(IdMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("idx_message_user_id", "user_id"),
        Index("idx_message_type", "message_type"),
        Index("idx_message_read_status", "read_status"),
        Index("idx_message_biz_no", "biz_no"),
        Index("idx_message_created_at", "created_at"),
        Index("idx_message_user_read_created", "user_id", "read_status", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    biz_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    biz_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNREAD", server_default="UNREAD")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLE", server_default="ENABLE")
