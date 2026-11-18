from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.exceptions import AppException
from app.core.security import create_access_token, is_admin_user, revoke_access_token
from app.models.user import User, UserLoginLog
from app.repositories.user import UserLoginLogRepository
from app.modules.auth.schemas import LoginRequest, LoginVO
from app.modules.quota.service import QuotaService
from app.modules.user.service import UserService


class AuthService:

    def __init__(self, db: Session) -> None:
        self.db = db
        self.login_log_repo = UserLoginLogRepository(db)
        self.user_service = UserService(db)
        self.quota_service = QuotaService(db)

    def login(self, request_data: LoginRequest, request: Request) -> LoginVO:
        try:
            from app.modules.auth.email_codes import EmailCodeService
            from app.modules.guest.service import GuestService, COOKIE
            guests = GuestService(self.db)
            identity = guests.from_cookie(request.cookies.get(COOKIE))
            # Validate migration prerequisites before consuming a one-time email code.
            if identity:
                guests.lock()
                guests._check_active(identity.user_id)
            EmailCodeService(self.db).verify(request_data.email, request_data.code)
            user = guests.convert(identity, request_data.email, request_data.inviteCode) if identity else self.user_service.register_email(request_data.email, request_data.inviteCode)
            quota = self.quota_service.get_or_init_quota(user.id)
            self._save_login_log(
                user_id=user.id,
                mobile=request_data.email,
                request=request,
                status="SUCCESS",
                remark="登录成功",
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return LoginVO(
            guestConverted=identity is not None,
            token=create_access_token(user.id),
            uid=user.uid,
            userId=user.id,
            mobile=user.mobile,
            email=user.email,
            nickname=user.nickname,
            inviteCode=user.invite_code,
            vipExpireTime=user.vip_expire_time,
            remainingPoints=quota.remaining_points or 0,
            admin=is_admin_user(user),
        )

    def logout(self, token: str) -> None:
        revoke_access_token(token, self.db)

    def _save_login_log(
        self,
        user_id: int,
        mobile: str,
        request: Request,
        status: str,
        remark: str,
    ) -> None:
        user_agent = request.headers.get("user-agent")
        client_host = request.client.host if request.client else None
        self.login_log_repo.add(
            UserLoginLog(
                user_id=user_id,
                login_type="EMAIL_CODE",
                client_ip=client_host,
                user_agent=user_agent,
                device_id=mobile[:128],
                status=status,
                remark=remark,
            )
        )
