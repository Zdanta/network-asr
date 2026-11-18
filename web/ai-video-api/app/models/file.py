from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class FileRecord(IdMixin, Base):
    __tablename__ = "file_record"
    __table_args__ = (
        UniqueConstraint("file_no", name="uk_file_record_file_no"),
        Index("idx_file_record_user_id", "user_id"),
        Index("idx_file_record_file_type", "file_type"),
        Index("idx_file_record_status", "status"),
        Index("idx_file_record_created_at", "created_at"),
    )

    file_no: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOADED", server_default="UPLOADED")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
