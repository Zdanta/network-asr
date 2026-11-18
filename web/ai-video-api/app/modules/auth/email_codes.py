import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.email_verification import EmailVerification, EmailSendLimit
from app.modules.auth.mailer import send_verification_email


def digest(email: str, nonce: str, code: str) -> str:
    return hmac.new(get_settings().auth_token_secret.encode(), f"{email}:{nonce}:{code}".encode(), hashlib.sha256).hexdigest()


def locked_row(db, model, key, values):
    row = db.get(model, key)
    if row is None:
        try:
            with db.begin_nested():
                db.add(model(**values))
                db.flush()
        except IntegrityError:
            pass
    pk = model.email if model is EmailVerification else model.identity
    return db.scalar(select(model).where(pk == key).with_for_update().execution_options(populate_existing=True))


class EmailCodeService:
    def __init__(self, db):
        self.db = db

    def send(self, email: str, ip: str):
        now = datetime.now()
        ip_key = hashlib.sha256(ip.encode()).hexdigest()
        limit = locked_row(self.db, EmailSendLimit, ip_key,
                           {"identity": ip_key, "window_start": now, "send_count": 0})
        if limit.window_start <= now - timedelta(hours=1):
            limit.window_start, limit.send_count = now, 0
        if limit.send_count >= 20:
            self.db.rollback()
            raise AppException(code=1011, message="发送过于频繁，请一小时后重试", status_code=429)
        row = locked_row(self.db, EmailVerification, email, {"email": email, "nonce": "", "code_hash": "",
            "expires_at": now, "sent_at": now - timedelta(minutes=1), "window_start": now,
            "send_count": 0, "attempts": 0, "state": "NEW"})
        if row.send_count > 0 and row.sent_at > now - timedelta(seconds=60):
            self.db.rollback()
            raise AppException(code=1011, message="请60秒后再次获取验证码", status_code=429)
        if row.window_start <= now - timedelta(hours=1):
            row.window_start, row.send_count = now, 0
        if row.send_count >= 5:
            self.db.rollback()
            raise AppException(code=1011, message="该邮箱发送次数已达上限，请一小时后重试", status_code=429)
        code, nonce = f"{secrets.randbelow(1000000):06d}", secrets.token_hex(16)
        row.nonce, row.code_hash = nonce, digest(email, nonce, code)
        row.sent_at, row.expires_at, row.attempts, row.state = now, now + timedelta(minutes=10), 0, "SENDING"
        row.send_count += 1
        limit.send_count += 1
        self.db.commit()
        try:
            send_verification_email(email, code)
        except Exception:
            self.db.execute(update(EmailVerification).where(EmailVerification.email == email,
                EmailVerification.nonce == nonce).values(state="FAILED"))
            self.db.commit()
            raise
        self.db.execute(update(EmailVerification).where(EmailVerification.email == email,
            EmailVerification.nonce == nonce, EmailVerification.state == "SENDING").values(state="READY"))
        self.db.commit()
        return {"sent": True, "retryAfter": 60, "expiresIn": 600}

    def verify(self, email: str, code: str):
        row = self.db.scalar(select(EmailVerification).where(EmailVerification.email == email)
            .with_for_update().execution_options(populate_existing=True))
        if row is None or row.state != "READY" or row.expires_at <= datetime.now() or row.attempts >= 5:
            self.db.rollback()
            raise AppException(code=1001, message="验证码无效或已过期，请重新获取")
        if not hmac.compare_digest(row.code_hash, digest(email, row.nonce, code)):
            row.attempts += 1
            self.db.commit()
            raise AppException(code=1001, message="验证码不正确")
        row.state = "USED"
        self.db.flush()  # caller commits together with registration/binding
