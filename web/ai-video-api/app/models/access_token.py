from datetime import datetime
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RevokedAccessToken(Base):
    __tablename__ = "revoked_access_token"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
