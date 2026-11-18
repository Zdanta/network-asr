import secrets
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import is_admin_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.modules.quota.service import QuotaService
from app.modules.user.schemas import UserInfoVO


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.quota_service = QuotaService(db)

    def register_if_absent(self, mobile: str, invite_code: str | None) -> User:
        user = self.user_repo.get_by_mobile(mobile)
        if user is not None:
            self._bind_inviter_if_allowed(user, invite_code)
            self.quota_service.get_or_init_quota(user.id)
            return user

        user = User(
            uid=str(uuid.uuid4()),
            mobile=mobile,
            nickname=self._build_default_nickname(mobile),
            invite_code=self._generate_unique_invite_code(),
            inviter_id=self._resolve_inviter_id(mobile, invite_code),
            status="ENABLE",
            remark="系统自动注册",
        )
        self.user_repo.add(user)
        self.quota_service.get_or_init_quota(user.id)
        return user

    def get_user_info(self, user: User) -> UserInfoVO:
        from app.modules.guest.service import is_guest
        quota = self.quota_service.get_quota_info(user)
        return UserInfoVO(
            uid=user.uid,
            userId=user.id,
            mobile=user.mobile,
            email=user.email,
            nickname=user.nickname,
            inviteCode=user.invite_code,
            vipExpireTime=user.vip_expire_time,
            remainingPoints=quota.remainingPoints,
            remainingCount=quota.remainingCount,
            admin=is_admin_user(user),
            guest=is_guest(self.db, user.id),
        )

    def register_email(self, email: str, invite_code: str | None) -> User:
        from datetime import datetime
        from sqlalchemy import select
        user = self.db.scalar(select(User).where(User.email == email).with_for_update())
        if user:
            if user.deleted or user.status != "ENABLE":
                raise AppException(code=1003, message="账号已停用，请联系管理员", status_code=403)
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now()
            # Referral attribution is fixed at first registration.
            return user
        inviter = self._get_inviter(invite_code.strip()) if invite_code and invite_code.strip() else None
        user = User(uid=str(uuid.uuid4()), email=email, email_verified_at=datetime.now(), mobile=None,
            nickname=email.split("@", 1)[0][:64], invite_code=self._generate_unique_invite_code(),
            inviter_id=inviter.id if inviter else None, status="ENABLE", remark="邮箱验证注册")
        self.user_repo.add(user)
        self.quota_service.get_or_init_quota(user.id)
        return user

    def _build_default_nickname(self, mobile: str) -> str:
        return f"用户{mobile[-4:]}"

    def _generate_unique_invite_code(self) -> str:
        for _ in range(10):
            invite_code = secrets.token_hex(4).upper()
            if self.user_repo.get_by_invite_code(invite_code) is None:
                return invite_code
        raise AppException(code=5000, message="邀请码生成失败，请稍后重试", status_code=500)

    def _resolve_inviter_id(self, mobile: str, invite_code: str | None) -> int | None:
        if not invite_code:
            return None
        inviter = self._get_inviter(invite_code)
        if inviter.mobile == mobile:
            raise AppException(code=2023, message="不能绑定自己的邀请码")
        return inviter.id

    def _bind_inviter_if_allowed(self, user: User, invite_code: str | None) -> None:
        if not invite_code:
            return
        normalized = invite_code.strip()
        if normalized == user.invite_code or normalized == user.mobile:
            raise AppException(code=2023, message="不能绑定自己的邀请码")
        inviter = self._get_inviter(normalized)
        if user.inviter_id is not None:
            if user.inviter_id == inviter.id:
                return
            raise AppException(code=2025, message="已经绑定过邀请关系")
        if user.id == inviter.id or user.mobile == inviter.mobile:
            raise AppException(code=2023, message="不能绑定自己的邀请码")
        user.inviter_id = inviter.id

    def _get_inviter(self, invite_code: str) -> User:
        from app.modules.guest.service import is_guest
        inviter = self.user_repo.get_by_invite_code(invite_code.strip())
        if inviter is None or inviter.status != "ENABLE" or is_guest(self.db, inviter.id):
            raise AppException(code=2022, message="邀请码无效")
        return inviter
