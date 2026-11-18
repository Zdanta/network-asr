from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class OpcpayTrialClaim(Base):
    __tablename__ = "opcpay_trial_claim"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class OpcpayOperation(IdMixin, Base):
    __tablename__ = "opcpay_operation"
    __table_args__ = (UniqueConstraint("kind", "user_id", "action_id", name="uk_opcpay_action"),
                      UniqueConstraint("biz_no", name="uk_opcpay_biz"),
                      Index("idx_opcpay_recovery", "kind", "state", "lease_until"))

    kind: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int] = mapped_column(BigInteger)
    action_id: Mapped[str] = mapped_column(String(64))
    biz_no: Mapped[str] = mapped_column(String(64))
    request_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    response_json: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    metadata_json: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    result_text: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    state: Mapped[str] = mapped_column(String(20), default="PENDING")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
