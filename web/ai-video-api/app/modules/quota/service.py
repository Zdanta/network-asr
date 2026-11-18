from datetime import datetime

from sqlalchemy import Integer, cast, func, literal, select, union_all, update
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.quota import QuotaLog, UserQuota
from app.models.user import User
from app.repositories.quota import QuotaLogRepository, UserQuotaRepository
from app.repositories.system import SysConfigRepository
from app.modules.quota.schemas import QuotaInfoVO, QuotaLogPageVO, QuotaLogVO

CHANGE_TYPE_DESCS = {
    "TRIAL_ARCHIVE": "访客额度归档",
    "CONSUME": "任务消耗",
    "PURCHASE": "购买增加",
    "REGISTER_GIFT": "注册送积分",
    "INVITE_REWARD": "邀请奖励",
    "ADMIN_GRANT": "后台发放",
    "ADMIN_DEDUCT": "后台扣减",
}


class QuotaService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.quota_repo = UserQuotaRepository(db)
        self.log_repo = QuotaLogRepository(db)
        self.config_repo = SysConfigRepository(db)

    def get_or_init_quota(self, user_id: int) -> UserQuota:
        quota = self.quota_repo.get_by_user_id(user_id)
        if quota is not None:
            return quota

        initial_points = self.load_initial_points()
        quota = UserQuota(
            user_id=user_id,
            remaining_points=initial_points,
            daily_free_used=0,
            status="ENABLE",
        )
        self.quota_repo.add(quota)
        self.log_repo.add(
            QuotaLog(
                user_id=user_id,
                change_type="REGISTER_GIFT",
                change_amount=initial_points,
                before_points=0,
                after_points=initial_points,
                biz_no=f"REGISTER-{user_id}",
                remark="新注册用户赠送积分",
            )
        )
        return quota

    def get_quota_info(self, user: User) -> QuotaInfoVO:
        from app.modules.guest.service import is_guest
        quota = self.get_or_init_quota(user.id)
        seconds_per_point = self.load_seconds_per_point()
        local_points = quota.remaining_points or 0
        purchased_points = 0
        if get_settings().opcpay_enabled and not is_guest(self.db, user.id):
            self.db.commit()
            purchased_points = self.load_purchased_points(user.id)
            # Re-read after the remote query so a concurrent local debit is not hidden.
            self.db.refresh(quota)
            local_points = quota.remaining_points or 0
        remaining_points = local_points + purchased_points
        vip = bool(user.vip_expire_time and user.vip_expire_time > datetime.now())
        return QuotaInfoVO(
            remainingPoints=remaining_points,
            remainingCount=remaining_points,
            localRemainingPoints=local_points,
            purchasedRemainingPoints=purchased_points,
            vip=vip,
            vipExpireTime=user.vip_expire_time,
            secondsPerPoint=seconds_per_point,
            pointsPerMinute=max(1, 60 // seconds_per_point) if seconds_per_point > 0 else 10,
        )

    @staticmethod
    def load_purchased_points(user_id: int) -> int:
        from app.modules.payment.opcpay_client import OpcpayClient
        access = OpcpayClient().access(user_id)
        if access.get("quota_unit") != "POINT" or type(access.get("remaining")) is not int or access["remaining"] < 0:
            raise AppException(code=3011, message="额度查询待确认，请稍后刷新", status_code=503)
        return access["remaining"]

    def ensure_has_balance(self, user_id: int) -> UserQuota:
        quota = self.get_or_init_quota(user_id)
        if (quota.remaining_points or 0) <= 0:
            raise AppException(code=2001, message="额度不足，请先购买额度")
        return quota

    def ensure_has_points(self, user_id: int, required_points: int) -> UserQuota:
        if required_points <= 0:
            raise AppException(code=1001, message="暂时无法预估所需额度")
        from app.modules.guest.service import is_guest
        if is_guest(self.db, user_id):
            quota = self.get_or_init_quota(user_id)
            if (quota.remaining_points or 0) < required_points:
                raise AppException(code=2101, message=f"本次预计需要 {required_points} 点，体验额度不足，请登录后购买额度", status_code=403)
            return quota
        if get_settings().opcpay_enabled:
            from app.modules.payment.opcpay_client import OpcpayClient
            local = self.get_or_init_quota(user_id)
            if (local.remaining_points or 0) >= required_points:
                return local
            self.db.commit()
            client = OpcpayClient()
            _, product = client.product()
            amount = 1 if product["quota_unit"] == "COUNT" else required_points
            access = client.access(user_id, amount)
            if access.get("access_granted") is not True or access.get("quota_unit") != product["quota_unit"]:
                raise AppException(code=2001, message="支付宝额度不足，请前往购买额度页面充值")
            return self.get_or_init_quota(user_id)
        if required_points <= 0:
            raise AppException(code=1001, message="暂时无法预估所需额度")
        quota = self.get_or_init_quota(user_id)
        if (quota.remaining_points or 0) < required_points:
            raise AppException(code=2001, message=f"额度不足，本次预计需要 {required_points} 点")
        return quota

    def estimate_points(self, duration_seconds: int | None) -> int:
        if not duration_seconds or duration_seconds <= 0:
            return 0
        seconds_per_point = max(self.load_seconds_per_point(), 1)
        return (duration_seconds + seconds_per_point - 1) // seconds_per_point

    def consume_quota_by_duration(self, user_id: int, duration_seconds: int | None, biz_no: str, remark: str) -> int:
        points = self.estimate_points(duration_seconds)
        return self.consume_points_once(user_id, points, biz_no, remark)

    def consume_points_once(self, user_id: int, points: int, biz_no: str, remark: str) -> int:
        if points <= 0:
            return 0
        from app.modules.guest.service import GuestService
        guest_service = GuestService(self.db)
        guest_service.prepare_consume(biz_no)
        self.get_or_init_quota(user_id)
        # MySQL user-row lock serializes balance and idempotency check in this transaction.
        quota = self.db.scalar(select(UserQuota).where(UserQuota.user_id == user_id, UserQuota.deleted == 0)
                               .with_for_update().execution_options(populate_existing=True))
        # Locking read sees the latest committed log even under MySQL REPEATABLE READ.
        existing = self.db.scalar(select(QuotaLog).where(QuotaLog.user_id == user_id,
            QuotaLog.biz_no == biz_no, QuotaLog.deleted == 0).with_for_update())
        if existing is not None:
            if existing.change_type != "CONSUME" or existing.change_amount != -points:
                raise AppException(code=3006, message="原任务扣费参数不一致，请联系管理员")
            guest_service.settle(biz_no, True)
            return points
        before_points = quota.remaining_points or 0
        if before_points < points:
            raise AppException(code=2001, message="额度不足，请先购买额度")

        after_points = before_points - points
        changed = self.db.execute(update(UserQuota).where(UserQuota.id == quota.id, UserQuota.remaining_points >= points)
            .values(remaining_points=UserQuota.remaining_points - points).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise AppException(code=2001, message="额度不足，请先购买额度")
        self.db.expire(quota)
        self.log_repo.add(
            QuotaLog(
                user_id=user_id,
                change_type="CONSUME",
                change_amount=-points,
                before_points=before_points,
                after_points=after_points,
                biz_no=biz_no,
                remark=remark,
            )
        )
        guest_service.settle(biz_no, True)
        return points

    def add_quota_once(self, user_id: int, points: int, biz_no: str, change_type: str, remark: str) -> bool:
        if points <= 0:
            return False
        if self.log_repo.get_by_biz_no(biz_no, user_id=user_id) is not None:
            return False

        quota = self.get_or_init_quota(user_id)
        before_points = quota.remaining_points or 0
        after_points = before_points + points
        quota.remaining_points = after_points
        self.log_repo.add(
            QuotaLog(
                user_id=user_id,
                change_type=change_type,
                change_amount=points,
                before_points=before_points,
                after_points=after_points,
                biz_no=biz_no,
                remark=remark,
            )
        )
        return True

    def list_quota_logs(
        self,
        user_id: int,
        change_type: str | None,
        page_no: int,
        page_size: int,
    ) -> QuotaLogPageVO:
        if get_settings().opcpay_enabled:
            return self._list_combined_logs(user_id, change_type, page_no, page_size)
        statement = (
            select(QuotaLog)
            .where(QuotaLog.user_id == user_id, QuotaLog.deleted == 0)
            .order_by(QuotaLog.created_at.desc(), QuotaLog.id.desc())
        )
        if change_type:
            statement = statement.where(QuotaLog.change_type == change_type)

        page = self.log_repo.page(PageParams(page_no=page_no, page_size=page_size), statement)
        return QuotaLogPageVO(
            records=[self._to_log_vo(item) for item in page.records],
            total=page.total,
            pageNo=page.pageNo,
            pageSize=page.pageSize,
            pages=page.pages,
        )

    def _list_combined_logs(self, user_id: int, change_type: str | None, page_no: int, page_size: int) -> QuotaLogPageVO:
        """Read-only projection: provider purchases never credit the local wallet a second time."""
        import json
        from app.models.opcpay import OpcpayOperation
        local = select(QuotaLog.id.label("id"), literal("LOCAL").label("source"), QuotaLog.created_at.label("time")).where(
            QuotaLog.user_id == user_id, QuotaLog.deleted == 0)
        status = func.json_extract(OpcpayOperation.metadata_json, "$.payment_status")
        purchases = select(OpcpayOperation.id.label("id"), literal("PURCHASE").label("source"), OpcpayOperation.created_at.label("time")).where(
            OpcpayOperation.user_id == user_id, OpcpayOperation.deleted == 0, OpcpayOperation.kind == "PURCHASE",
            # MySQL returns JSON strings with quotes; SQLite returns plain strings.
            status.in_(["PAID", "REFUNDED", '"PAID"', '"REFUNDED"']),
            func.json_extract(OpcpayOperation.metadata_json, "$.checked_at").is_not(None),
            cast(func.json_extract(OpcpayOperation.metadata_json, "$.quantity"), Integer) > 0,
            # Avoid duplicating an already recorded legacy purchase with the same business number.
            ~select(QuotaLog.id).where(QuotaLog.user_id == user_id, QuotaLog.deleted == 0,
                QuotaLog.change_type == "PURCHASE", QuotaLog.biz_no == OpcpayOperation.biz_no).exists())
        if change_type and change_type != "ALL":
            local = local.where(QuotaLog.change_type == change_type)
            if change_type != "PURCHASE":
                purchases = purchases.where(literal(False))
        combined = union_all(local, purchases).subquery()
        params = PageParams(page_no=page_no, page_size=page_size)
        total = self.db.scalar(select(func.count()).select_from(combined)) or 0
        rows = self.db.execute(select(combined).order_by(combined.c.time.desc(), combined.c.source.desc(), combined.c.id.desc())
                               .offset(params.offset).limit(params.page_size)).all()
        local_ids = [r.id for r in rows if r.source == "LOCAL"]
        purchase_ids = [r.id for r in rows if r.source == "PURCHASE"]
        logs = {r.id: r for r in self.db.scalars(select(QuotaLog).where(QuotaLog.user_id == user_id, QuotaLog.id.in_(local_ids)))}
        operations = {r.id: r for r in self.db.scalars(select(OpcpayOperation).where(OpcpayOperation.user_id == user_id,
                                                                                 OpcpayOperation.id.in_(purchase_ids)))}
        records = []
        for row in rows:
            if row.source == "LOCAL":
                records.append(self._to_log_vo(logs[row.id]))
                continue
            op = operations[row.id]
            meta = json.loads(op.metadata_json)
            name = str(meta.get("name") or "资源包")
            if meta["payment_status"] == "REFUNDED":
                name += "（已退款）"
            records.append(QuotaLogVO(changeType="PURCHASE", changeTypeDesc="购买增加",
                changeAmount=int(meta["quantity"]), afterPoints=None, bizNo=op.biz_no,
                remark=name, createdAt=op.created_at.strftime("%Y-%m-%d %H:%M:%S")))
        return QuotaLogPageVO(records=records, total=total, pageNo=page_no, pageSize=page_size,
                              pages=(total + page_size - 1) // page_size)

    def load_initial_points(self) -> int:
        return self._read_int_config("INIT_POINTS", get_settings().init_points)

    def load_seconds_per_point(self) -> int:
        return self._read_int_config("SECONDS_PER_POINT", get_settings().seconds_per_point)

    def _read_int_config(self, key: str, default: int) -> int:
        config = self.config_repo.get_by_key(key)
        if config is None or not config.config_value:
            return default
        try:
            return int(config.config_value)
        except ValueError:
            return default

    def _to_log_vo(self, log: QuotaLog) -> QuotaLogVO:
        return QuotaLogVO(
            changeType=log.change_type,
            changeTypeDesc=CHANGE_TYPE_DESCS.get(log.change_type, log.change_type),
            changeAmount=log.change_amount,
            afterPoints=log.after_points,
            bizNo=log.biz_no,
            remark=log.remark,
            createdAt=log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        )
