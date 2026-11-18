from app.common.clock import utc_naive_now
"""Guest identities and serialized, server-side trial limits. All stored IPs are keyed hashes."""
import hashlib
import hmac
import ipaddress
import secrets
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select, update, func
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.guest import GuestIdentity, GuestLimitLock, GuestReservation, GuestEvent
from app.models.user import User
from app.models.quota import UserQuota, QuotaLog
from app.models.task import Task
from app.models.media_import import MediaImportJob
from app.repositories.system import SysConfigRepository

COOKIE = "asr_guest"
POLICY = {"points": (100, 1, 1000), "ip_points": (300, 1, 100000), "global_points": (10000, 1, 1000000),
          "ip_claims": (3, 1, 100), "upload_mb": (50, 1, 100), "session_days": (7, 1, 30)}


def fingerprint(value):
    return hmac.new(get_settings().auth_token_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def client_ip(request):
    peer = request.client.host if request.client else "unknown"
    try:
        trusted = [ipaddress.ip_network(x.strip()) for x in get_settings().guest_trusted_proxies.split(",") if x.strip()]
        if any(ipaddress.ip_address(peer) in net for net in trusted):
            # Walk from the trusted server towards the client; ignore spoofed left-hand entries.
            chain = request.headers.get("x-forwarded-for", "").split(",")
            for address in reversed(chain):
                candidate = ipaddress.ip_address(address.strip())
                if not any(candidate in net for net in trusted):
                    return str(candidate)
    except ValueError:
        pass
    return peer


def identity_for(db, user_id):
    return db.get(GuestIdentity, user_id)


def is_guest(db, user_id):
    identity = identity_for(db, user_id)
    return bool(identity and identity.state == "GUEST")


class GuestService:
    def __init__(self, db):
        self.db = db

    def policy(self):
        settings = get_settings()
        repo = SysConfigRepository(self.db)
        result = {"enabled": getattr(settings, "guest_enabled", False)}
        enabled = repo.get_by_key("GUEST_ENABLED")
        if enabled:
            result["enabled"] = enabled.config_value.lower() in {"true", "1"}
        for key, (default, low, high) in POLICY.items():
            row = repo.get_by_key("GUEST_" + key.upper())
            try:
                value = int(row.config_value) if row and row.config_value else getattr(settings, "guest_" + key, default)
            except (ValueError, TypeError):
                value = default
            result[key] = min(high, max(low, int(value)))
        return result

    def lock(self):
        # A single short DB critical section serializes claims, quota reservations and migration.
        # Never hold it during HTTP, downloads, uploads or ASR.
        if self.db.bind.dialect.name == "mysql":
            from sqlalchemy.dialects.mysql import insert
            statement = insert(GuestLimitLock).values(key="trial")
            statement = statement.on_duplicate_key_update(key=statement.inserted.key)
        else:
            from sqlalchemy.dialects.sqlite import insert
            statement = insert(GuestLimitLock).values(key="trial").on_conflict_do_nothing()
        self.db.execute(statement)
        self.db.scalar(select(GuestLimitLock).where(GuestLimitLock.key == "trial").with_for_update())

    def from_cookie(self, token):
        if not token or len(token) > 128:
            return None
        identity = self.db.scalar(select(GuestIdentity).where(GuestIdentity.session_hash == fingerprint("session:" + token)))
        if not identity or identity.state != "GUEST" or identity.expires_at <= utc_naive_now():
            return None
        return identity

    def claim(self, device_id, token, ip):
        policy = self.policy()
        if not policy["enabled"]:
            raise AppException(code=2101, message="免注册体验暂未开放，请登录后继续", status_code=403)
        self.lock()
        existing = self.from_cookie(token)
        if existing:
            return existing.user_id, None
        device_hash, ip_hash = fingerprint("device:" + device_id), fingerprint("ip:" + ip)
        old = self.db.scalar(select(GuestIdentity).where(GuestIdentity.device_hash == device_hash).with_for_update())
        if old:
            raise AppException(code=2101, message="此设备已领取体验额度，请登录后继续", status_code=403)
        since = utc_naive_now() - timedelta(hours=24)
        claims = list(self.db.scalars(select(GuestIdentity).where(GuestIdentity.ip_hash == ip_hash,
            GuestIdentity.created_at >= since).with_for_update()))
        if len(claims) >= policy["ip_claims"]:
            raise AppException(code=2101, message="当前网络体验次数已达上限，请通过邮箱登录后继续", status_code=429)
        # Also bound account creation globally, before any download/ASR takes place.
        recent = list(self.db.scalars(select(GuestIdentity.user_id).where(GuestIdentity.created_at >= since).with_for_update()))
        if len(recent) >= max(10, policy["global_points"] // policy["points"] * 3):
            raise AppException(code=2101, message="今日体验名额已满，请登录后继续", status_code=429)
        user = User(uid=str(uuid.uuid4()), nickname="体验用户", invite_code=secrets.token_hex(12).upper(), status="ENABLE", remark="免注册体验")
        self.db.add(user)
        self.db.flush()
        secret = secrets.token_urlsafe(32)
        now = utc_naive_now()
        identity = GuestIdentity(user_id=user.id, device_hash=device_hash, session_hash=fingerprint("session:" + secret),
            ip_hash=ip_hash, initial_points=policy["points"], created_at=now,
            expires_at=now + timedelta(days=policy["session_days"]), state="GUEST")
        self.db.add_all([identity, UserQuota(user_id=user.id, remaining_points=policy["points"]),
            QuotaLog(user_id=user.id, change_type="REGISTER_GIFT", change_amount=policy["points"], before_points=0,
                after_points=policy["points"], biz_no="REGISTER-" + str(user.id), remark="新用户免注册体验赠送")])
        self.db.commit()
        return user.id, secret

    def _reconcile(self, user_id):
        reservations = list(self.db.scalars(select(GuestReservation).where(GuestReservation.user_id == user_id,
            GuestReservation.state == "RESERVED").with_for_update()))
        for reservation in reservations:
            task = self.db.scalar(select(Task).where(Task.task_no == reservation.task_no).with_for_update()
                                  .execution_options(populate_existing=True))
            if task and task.status in {"FAIL", "SUCCESS"}:
                consumed = self.db.scalar(select(QuotaLog.id).where(QuotaLog.biz_no == task.task_no, QuotaLog.change_type == "CONSUME").with_for_update())
                reservation.state = "CONSUMED" if consumed else "RELEASED"
        self.db.flush()

    def _available(self, identity):
        self._reconcile(identity.user_id)
        quota = self.db.scalar(select(UserQuota).where(UserQuota.user_id == identity.user_id).with_for_update()
                               .execution_options(populate_existing=True))
        held = list(self.db.scalars(select(GuestReservation).where(GuestReservation.user_id == identity.user_id,
            GuestReservation.state == "RESERVED").with_for_update()))
        return max(0, (quota.remaining_points or 0) - sum(r.points for r in held))

    def _check_active(self, user_id, *, allow_import=False):
        active = self.db.scalar(select(Task.id).where(Task.user_id == user_id, Task.status.in_(["INIT", "PROCESSING"])).with_for_update())
        imports = list(self.db.scalars(select(MediaImportJob).where(MediaImportJob.user_id == user_id,
            MediaImportJob.status.in_(["INIT", "PROCESSING"])).with_for_update()))
        if active or (imports and not allow_import):
            raise AppException(code=2102, message="已有体验任务正在处理，请完成后再提交", status_code=409)

    def gate_request(self, user_id, kind):
        if not is_guest(self.db, user_id):
            return None
        policy = self.policy()
        self.lock()
        identity = self.db.scalar(select(GuestIdentity).where(GuestIdentity.user_id == user_id).with_for_update()
                                  .execution_options(populate_existing=True))
        if identity.state != "GUEST":
            raise AppException(code=2101, message="账号状态已更新，请刷新后继续", status_code=409)
        if not policy["enabled"] or identity.expires_at <= utc_naive_now():
            raise AppException(code=2101, message="体验已结束，请登录后继续", status_code=403)
        self._check_active(user_id)
        if identity.upload_until and identity.upload_until > utc_naive_now():
            raise AppException(code=2102, message="文件正在上传，请稍候", status_code=409)
        if self._available(identity) < 1:
            raise AppException(code=2101, message="体验额度已用完，请登录后购买额度", status_code=403)
        self._check_budget(identity, 1, policy)
        events = list(self.db.scalars(select(GuestEvent).where(GuestEvent.ip_hash == identity.ip_hash,
            GuestEvent.created_at >= utc_naive_now() - timedelta(hours=24)).with_for_update()))
        if len(events) >= 30 or sum(e.user_id == user_id for e in events) >= 10:
            raise AppException(code=2101, message="体验提交过于频繁，请通过邮箱登录后继续", status_code=429)
        self.db.add(GuestEvent(user_id=user_id, ip_hash=identity.ip_hash, kind=kind, created_at=utc_naive_now()))
        if kind == "UPLOAD":
            identity.upload_lease = str(uuid.uuid4())
            identity.upload_until = utc_naive_now() + timedelta(minutes=5)
            lease = identity.upload_lease
            self.db.commit()
            return lease
        return None  # Import insertion commits atomically with its rate-limit event.

    def release_upload(self, user_id, lease):
        if lease:
            self.db.execute(update(GuestIdentity).where(GuestIdentity.user_id == user_id, GuestIdentity.upload_lease == lease)
                .values(upload_lease=None, upload_until=None))
            self.db.commit()

    def reserve(self, user_id, task_no, points, *, allow_import=False):
        if not is_guest(self.db, user_id):
            return False
        policy = self.policy()
        self.lock()
        identity = self.db.scalar(select(GuestIdentity).where(GuestIdentity.user_id == user_id).with_for_update()
                                  .execution_options(populate_existing=True))
        if identity.state != "GUEST" or not policy["enabled"]:
            raise AppException(code=2101, message="请登录后继续处理", status_code=403)
        self._check_active(user_id, allow_import=allow_import)
        if points <= 0 or self._available(identity) < points:
            raise AppException(code=2101, message=f"本次预计需要 {points} 点，体验额度不足，请登录后购买额度", status_code=403)
        self._check_budget(identity, points, policy)
        self.db.add(GuestReservation(task_no=task_no, user_id=user_id, ip_hash=identity.ip_hash, points=points,
                                     state="RESERVED", created_at=utc_naive_now()))
        self.db.flush()
        return True

    def _check_budget(self, identity, points, policy):
        rows = list(self.db.scalars(select(GuestReservation).where(
            GuestReservation.created_at >= utc_naive_now() - timedelta(hours=24),
            GuestReservation.state.in_(["RESERVED", "CONSUMED"])).with_for_update()))
        global_used = sum(r.points for r in rows)
        ip_used = sum(r.points for r in rows if r.ip_hash == identity.ip_hash)
        if global_used + points > policy["global_points"] or ip_used + points > policy["ip_points"]:
            raise AppException(code=2101, message="当前网络或本站免费体验额度已达上限，请登录后继续", status_code=429)

    def before_asr(self, task_no):
        reservation = self.db.get(GuestReservation, task_no)
        if not reservation:
            return
        self.lock()
        reservation = self.db.scalar(select(GuestReservation).where(GuestReservation.task_no == task_no).with_for_update()
                                      .execution_options(populate_existing=True))
        if reservation.state not in {"RESERVED", "CONSUMED"}:
            raise AppException(code=2101, message="体验预留额度已失效，请登录后继续")
        self.db.commit()  # Do not carry locks into media work.

    def prepare_consume(self, task_no):
        if self.db.get(GuestReservation, task_no):
            self.lock()

    def settle(self, task_no, consumed):
        reservation = self.db.get(GuestReservation, task_no)
        if reservation:
            self.lock()
            reservation = self.db.scalar(select(GuestReservation).where(GuestReservation.task_no == task_no).with_for_update()
                                          .execution_options(populate_existing=True))
            if reservation.state != "CONSUMED":
                reservation.state = "CONSUMED" if consumed else "RELEASED"

    def convert(self, identity, email, invite_code):
        from app.models.file import FileRecord
        from app.models.opcpay import OpcpayOperation
        from app.modules.user.service import UserService
        self.lock()
        identity = self.db.scalar(select(GuestIdentity).where(GuestIdentity.user_id == identity.user_id).with_for_update()
                                  .execution_options(populate_existing=True))
        if identity.state != "GUEST":
            raise AppException(code=2101, message="体验账号已升级，请重新登录", status_code=409)
        account = self.db.scalar(select(User).where(User.email == email).with_for_update())
        guest = self.db.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        self._check_active(guest.id)
        if identity.upload_until and identity.upload_until > utc_naive_now():
            raise AppException(code=2102, message="文件正在上传，请上传完成后再登录", status_code=409)
        if account and (account.deleted or account.status != "ENABLE"):
            raise AppException(code=1003, message="账号已停用", status_code=403)
        if not account:
            guest.email, guest.email_verified_at, guest.nickname = email, datetime.now(), email.split("@", 1)[0][:64]
            if invite_code:
                inviter = UserService(self.db)._get_inviter(invite_code.strip())
                if inviter.id != guest.id:
                    guest.inviter_id = inviter.id
            identity.state, identity.converted_at = "FORMAL", utc_naive_now()
            return guest
        self._reconcile(guest.id)
        source_quota = self.db.scalar(select(UserQuota).where(UserQuota.user_id == guest.id).with_for_update())
        target_quota = self.db.scalar(select(UserQuota).where(UserQuota.user_id == account.id).with_for_update()
                                     .execution_options(populate_existing=True))
        if target_quota is None:
            target_quota = UserQuota(user_id=account.id, remaining_points=0)
            self.db.add(target_quota)
        already_gifted = self.db.scalar(select(QuotaLog.id).where(QuotaLog.user_id == account.id,
            QuotaLog.change_type == "REGISTER_GIFT").with_for_update())
        left = source_quota.remaining_points or 0
        if already_gifted and left:
            self.db.add(QuotaLog(user_id=guest.id, change_type="TRIAL_ARCHIVE", change_amount=-left,
                before_points=left, after_points=0, biz_no="ARCHIVE-" + str(guest.id), remark="访客额度归档，已有账号不重复领取新用户赠送"))
            self.db.flush()
        elif left:
            target_quota.remaining_points = (target_quota.remaining_points or 0) + left
        source_quota.remaining_points = 0
        for model in (FileRecord, Task, MediaImportJob, QuotaLog, OpcpayOperation):
            self.db.execute(update(model).where(model.user_id == guest.id).values(user_id=account.id))
        identity.state, identity.target_user_id, identity.converted_at = "MERGED", account.id, utc_naive_now()
        guest.status = "DISABLE"
        return account
