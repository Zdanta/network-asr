from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class SysConfig(IdMixin, Base):
    __tablename__ = "sys_config"
    __table_args__ = (
        UniqueConstraint("config_key", name="uk_sys_config_key"),
        Index("idx_sys_config_status", "status"),
    )

    config_key: Mapped[str] = mapped_column(String(64), nullable=False)
    config_value: Mapped[str] = mapped_column(String(512), nullable=False)
    config_name: Mapped[str] = mapped_column(String(128), nullable=False)
    config_desc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLE", server_default="ENABLE")
