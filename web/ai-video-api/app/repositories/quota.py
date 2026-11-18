from sqlalchemy import select

from app.models.quota import QuotaLog, UserQuota
from app.repositories.base import BaseRepository


class UserQuotaRepository(BaseRepository[UserQuota]):
    model = UserQuota

    def get_by_user_id(self, user_id: int) -> UserQuota | None:
        return self.session.execute(
            select(UserQuota).where(UserQuota.user_id == user_id, UserQuota.deleted == 0)
        ).scalar_one_or_none()


class QuotaLogRepository(BaseRepository[QuotaLog]):
    model = QuotaLog

    def get_by_biz_no(self, biz_no: str, user_id: int | None = None) -> QuotaLog | None:
        statement = select(QuotaLog).where(QuotaLog.biz_no == biz_no, QuotaLog.deleted == 0)
        if user_id is not None:
            statement = statement.where(QuotaLog.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()
