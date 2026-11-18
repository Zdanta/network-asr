import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models.user import User
from app.repositories.user import UserRepository

_REVOKED_TOKENS: set[str] = set()


@dataclass(frozen=True)
class CurrentUser:
    id: int
    uid: str
    mobile: str | None
    is_admin: bool
    is_guest: bool = False


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(12)
    payload = f"{user_id}:{issued_at}:{nonce}"
    payload_b64 = _urlsafe_b64encode(payload.encode("utf-8"))
    signature = hmac.new(settings.auth_token_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_urlsafe_b64encode(signature)}"


def revoke_access_token(token: str, db: Session | None = None) -> None:
    if db is not None:
        from app.models.access_token import RevokedAccessToken
        db.merge(RevokedAccessToken(token_hash=hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    _REVOKED_TOKENS.add(token)


def parse_access_token(token: str, db: Session | None = None) -> int:
    if not token or token in _REVOKED_TOKENS:
        raise AppException(code=1002, message="请先登录后再继续", status_code=401)
    if db is not None:
        from app.models.access_token import RevokedAccessToken
        if db.get(RevokedAccessToken, hashlib.sha256(token.encode()).hexdigest()) is not None:
            raise AppException(code=1002, message="请先登录后再继续", status_code=401)

    settings = get_settings()
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        expected_signature = hmac.new(
            settings.auth_token_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _urlsafe_b64decode(signature_b64)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("invalid token signature")

        payload = _urlsafe_b64decode(payload_b64).decode("utf-8")
        user_id_text, issued_at_text, _ = payload.split(":", 2)
        if settings.auth_token_expire_seconds > 0 and int(time.time()) - int(issued_at_text) > settings.auth_token_expire_seconds:
            raise ValueError("token expired")
        return int(user_id_text)
    except Exception as exc:
        raise AppException(code=1002, message="请先登录后再继续", status_code=401) from exc


def create_download_ticket(user_id: int, task_no: str) -> tuple[str, int]:
    settings = get_settings()
    expires_at = int(time.time()) + max(10, settings.download_ticket_expire_seconds)
    nonce = secrets.token_urlsafe(8)
    payload = f"{user_id}:{task_no}:{expires_at}:{nonce}"
    payload_b64 = _urlsafe_b64encode(payload.encode("utf-8"))
    signature = hmac.new(
        settings.auth_token_secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_urlsafe_b64encode(signature)}", expires_at


def parse_download_ticket(ticket: str) -> tuple[int, str]:
    settings = get_settings()
    try:
        payload_b64, signature_b64 = ticket.split(".", 1)
        expected_signature = hmac.new(
            settings.auth_token_secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _urlsafe_b64decode(signature_b64)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("invalid ticket signature")

        payload = _urlsafe_b64decode(payload_b64).decode("utf-8")
        user_id_text, task_no, expires_at_text, _ = payload.split(":", 3)
        if int(time.time()) > int(expires_at_text):
            raise ValueError("ticket expired")
        return int(user_id_text), task_no
    except Exception as exc:
        raise AppException(code=1002, message="下载链接已失效，请重新获取", status_code=401) from exc


def extract_token(request: Request) -> str:
    token = request.headers.get("satoken")
    if token:
        return token

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    raise AppException(code=1002, message="请先登录后再继续", status_code=401)


def is_admin_mobile(mobile: str | None) -> bool:
    return bool(mobile and mobile in get_settings().admin_mobiles)


def is_admin_user(user: User) -> bool:
    emails = {email.strip().lower() for email in get_settings().admin_email_whitelist.split(",") if email.strip()}
    return is_admin_mobile(user.mobile) or bool(user.email and user.email.lower() in emails)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    from app.modules.guest.service import GuestService, COOKIE, is_guest
    if request.headers.get("satoken") or request.headers.get("authorization"):
        user_id = parse_access_token(extract_token(request), db)
    else:
        identity = GuestService(db).from_cookie(request.cookies.get(COOKIE))
        if not identity:
            raise AppException(code=1002, message="请登录或开始免注册体验", status_code=401)
        user_id = identity.user_id
    user = UserRepository(db).get(user_id)
    if user is None or user.deleted != 0 or user.status != "ENABLE":
        raise AppException(code=1002, message="请先登录后再继续", status_code=401)
    guest = is_guest(db, user.id)
    return CurrentUser(id=user.id, uid=user.uid, mobile=user.mobile, is_admin=not guest and is_admin_user(user), is_guest=guest)


def get_registered_user(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current.is_guest:
        raise AppException(code=2101, message="请先通过邮箱登录，再购买或管理账户", status_code=403)
    return current


def get_current_user_model(request: Request, db: Session = Depends(get_db)) -> User:
    current_user = get_current_user(request, db)
    user = UserRepository(db).get(current_user.id)
    if user is None:
        raise AppException(code=1002, message="请先登录后再继续", status_code=401)
    return user
