from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, extract_token, get_current_user, get_registered_user
from app.modules.auth.schemas import LoginRequest, LoginVO, LogoutVO, EmailRequest, BindEmailRequest
from app.modules.auth.service import AuthService

router = APIRouter()


@router.post("/email-code", response_model=ApiResponse[dict])
def send_email_code(body: EmailRequest, request: Request, db: Session = Depends(get_db)):
    from app.modules.auth.email_codes import EmailCodeService
    from app.modules.guest.service import client_ip
    return success_response(EmailCodeService(db).send(body.email, client_ip(request)))


@router.post("/bind-email", response_model=ApiResponse[dict])
def bind_email(body: BindEmailRequest, user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    from datetime import datetime
    from sqlalchemy import select
    from app.models.user import User
    from app.modules.auth.email_codes import EmailCodeService
    from app.core.exceptions import AppException
    try:
        EmailCodeService(db).verify(body.email, body.code)
        existing = db.scalar(select(User).where(User.email == body.email).with_for_update())
        if existing is not None and existing.id != user.id:
            raise AppException(code=1001, message="该邮箱已绑定其他账号，不能合并账号")
        account = db.scalar(select(User).where(User.id == user.id).with_for_update())
        if account.email and account.email != body.email:
            raise AppException(code=1001, message="当前账号已绑定邮箱，请联系管理员更换")
        account.email, account.email_verified_at = body.email, datetime.now()
        db.commit()
        return success_response({"email": body.email})
    except Exception:
        db.rollback()
        raise


@router.post("/login", response_model=ApiResponse[LoginVO])
def login(
    login_request: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[LoginVO]:
    result = AuthService(db).login(login_request, request)
    from app.modules.guest.service import COOKIE
    response.delete_cookie(COOKIE, path="/")
    return success_response(result)


@router.post("/logout", response_model=ApiResponse[LogoutVO])
def logout(
    request: Request,
    response: Response,
    _: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[LogoutVO]:
    from app.modules.guest.service import GuestService, COOKIE
    if request.headers.get("satoken") or request.headers.get("authorization"):
        AuthService(db).logout(extract_token(request))
    else:
        from datetime import datetime
        identity = GuestService(db).from_cookie(request.cookies.get(COOKIE))
        if identity:
            identity.expires_at = datetime.utcnow()
            db.commit()
    response.delete_cookie(COOKIE, path="/")
    return success_response(LogoutVO())
