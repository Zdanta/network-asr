from sqlalchemy import BigInteger, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class MediaImportJob(IdMixin, Base):
    __tablename__ = "media_import_job"
    __table_args__ = (
        UniqueConstraint("job_id", name="uk_media_import_job_job_id"),
        Index("idx_media_import_job_user_id", "user_id"),
        Index("idx_media_import_job_status", "status"),
        Index("idx_media_import_job_task_no", "task_no"),
        Index("idx_media_import_job_created_at", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="INIT", server_default="INIT")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    task_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    download_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cookie_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
