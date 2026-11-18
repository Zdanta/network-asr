from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class Task(IdMixin, Base):
    __tablename__ = "task"
    __table_args__ = (
        UniqueConstraint("task_no", name="uk_task_task_no"),
        Index("idx_task_user_id", "user_id"),
        Index("idx_task_file_id", "file_id"),
        Index("idx_task_status", "status"),
        Index("idx_task_created_at", "created_at"),
        Index("idx_task_user_status", "user_id", "status"),
    )

    task_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="INIT", server_default="INIT")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    more_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
