from sqlalchemy import func, select

from app.models.user import User, UserLoginLog
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_uid(self, uid: str) -> User | None:
        return self.session.execute(select(User).where(User.uid == uid, User.deleted == 0)).scalar_one_or_none()

    def get_by_mobile(self, mobile: str) -> User | None:
        return self.session.execute(select(User).where(User.mobile == mobile, User.deleted == 0)).scalar_one_or_none()

    def get_by_invite_code(self, invite_code: str) -> User | None:
        return self.session.execute(
            select(User).where(User.invite_code == invite_code, User.deleted == 0)
        ).scalar_one_or_none()

    def count_by_inviter_id(self, inviter_id: int) -> int:
        return self.session.execute(
            select(func.count()).select_from(User).where(User.inviter_id == inviter_id, User.deleted == 0)
        ).scalar_one()

    def list_by_ids(self, ids: list[int]) -> list[User]:
        if not ids:
            return []
        return self.session.execute(select(User).where(User.id.in_(ids), User.deleted == 0)).scalars().all()


class UserLoginLogRepository(BaseRepository[UserLoginLog]):
    model = UserLoginLog
