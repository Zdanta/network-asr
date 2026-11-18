import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.exceptions import AppException
from app.core.config import get_settings
from app.modules.quota.service import QuotaService
from app.models.opcpay import OpcpayOperation
from app.models.guest import GuestIdentity
from app.models.payment import PayOrder
from app.models.quota import QuotaLog, UserQuota
from app.models.task import Task
from app.models.user import User
from app.models.withdrawal import WithdrawalOrder
from app.modules.admin.schemas import (
    AdminDashboardOverviewVO,
    AdminQuotaAdjustRequest,
    AdminUserDetailVO,
    AdminUserPageVO,
    AdminUserVO,
    AdminWithdrawalPageVO,
    AdminWithdrawalStatusRequest,
    AdminWithdrawalVO,
)
from app.repositories.payment import PayOrderRepository
from app.repositories.quota import QuotaLogRepository, UserQuotaRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.repositories.withdrawal import WithdrawalOrderRepository

ZERO = Decimal("0.00")


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.quota_repo = UserQuotaRepository(db)
        self.quota_log_repo = QuotaLogRepository(db)
        self.task_repo = TaskRepository(db)
        self.pay_order_repo = PayOrderRepository(db)
        self.withdrawal_repo = WithdrawalOrderRepository(db)

    def get_dashboard_overview(self) -> AdminDashboardOverviewVO:
        start_of_day = datetime.combine(datetime.now().date(), time.min)
        end_of_day = datetime.combine(datetime.now().date(), time.max)
        from app.modules.admin.orders import AdminOrderService
        paid_count, paid_amount = AdminOrderService(self.db).confirmed_today()
        pending_withdrawal_amount = self._sum_decimal(
            select(func.coalesce(func.sum(WithdrawalOrder.amount), 0)).where(
                WithdrawalOrder.status == "PENDING",
                WithdrawalOrder.deleted == 0,
            )
        )
        return AdminDashboardOverviewVO(
            totalUsers=self._count(User, self._registered_condition()),
            todayNewUsers=self._count(User, self._new_registered_condition(start_of_day, end_of_day)),
            todayTasks=self._count(Task, Task.created_at >= start_of_day, Task.created_at <= end_of_day),
            todaySuccessTasks=self._count(
                Task,
                Task.status == "SUCCESS",
                Task.created_at >= start_of_day,
                Task.created_at <= end_of_day,
            ),
            todayFailTasks=self._count(
                Task,
                Task.status == "FAIL",
                Task.created_at >= start_of_day,
                Task.created_at <= end_of_day,
            ),
            todayPaidOrders=paid_count,
            todayPaidAmount=paid_amount,
            pendingFailTasks=self._count(Task, Task.status == "FAIL"),
            pendingWithdrawals=self._count(WithdrawalOrder, WithdrawalOrder.status == "PENDING"),
            pendingWithdrawalAmount=pending_withdrawal_amount,
        )

    def list_users(self, keyword: str | None, page_no: int, page_size: int) -> AdminUserPageVO:
        params = PageParams(page_no=max(page_no, 1), page_size=max(1, min(page_size, 100)))
        statement = select(User).where(User.deleted == 0, self._registered_condition()).order_by(User.created_at.desc(), User.id.desc())
        if keyword:
            like = f"%{keyword.strip()}%"
            statement = statement.where(
                or_(
                    User.mobile.like(like),
                    User.email.like(like),
                    User.uid.like(like),
                    User.invite_code.like(like),
                    User.nickname.like(like),
                )
            )

        total = self.db.execute(select(func.count()).select_from(statement.order_by(None).subquery())).scalar_one()
        users = self.db.execute(statement.offset(params.offset).limit(params.page_size)).scalars().all()
        balances = self._quota_balances([user.id for user in users])
        return AdminUserPageVO(
            pageNo=params.page_no,
            pageSize=params.page_size,
            total=total,
            hasMore=params.offset + len(users) < total,
            records=[self._to_user_vo(user, balances[user.id]) for user in users],
        )

    def get_user_detail(self, uid: str) -> AdminUserDetailVO:
        return self._to_user_detail_vo(self._get_user_by_uid_required(uid))

    def adjust_user_quota(self, request_data: AdminQuotaAdjustRequest) -> AdminUserDetailVO:
        if request_data.points == 0:
            raise AppException(code=1001, message="调整额度不能为 0")

        user = self._get_user_by_uid_required(request_data.uid)
        # Fetch provider data before writing; a provider timeout must not turn a committed adjustment into a failed response.
        purchased = self._quota_balances([user.id])[user.id][1]
        self.db.scalar(select(User).where(User.id == user.id).with_for_update())
        quota = self._get_or_init_zero_quota(user.id)
        self.db.flush()
        quota = self.db.scalar(select(UserQuota).where(UserQuota.id == quota.id).with_for_update()
                               .execution_options(populate_existing=True))
        before_points = quota.remaining_points or 0
        after_points = before_points + request_data.points
        if after_points < 0:
            raise AppException(code=2001, message="调整后额度不能小于 0")

        quota.remaining_points = after_points
        self.quota_log_repo.add(
            QuotaLog(
                user_id=user.id,
                change_type="ADMIN_GRANT" if request_data.points > 0 else "ADMIN_DEDUCT",
                change_amount=request_data.points,
                before_points=before_points,
                after_points=after_points,
                biz_no=self._generate_admin_biz_no(),
                remark=request_data.remark.strip(),
            )
        )
        self.db.commit()
        return self._to_user_detail_vo(user, (after_points, purchased))

    def list_withdrawals(
        self,
        status: str | None,
        keyword: str | None,
        page_no: int,
        page_size: int,
    ) -> AdminWithdrawalPageVO:
        params = PageParams(page_no=max(page_no, 1), page_size=max(1, min(page_size, 100)))
        statement = (
            select(WithdrawalOrder, User)
            .join(User, WithdrawalOrder.user_id == User.id)
            .where(WithdrawalOrder.deleted == 0, User.deleted == 0)
            .order_by(WithdrawalOrder.created_at.desc(), WithdrawalOrder.id.desc())
        )
        if status:
            normalized_status = status.strip().upper()
            if normalized_status not in {"PENDING", "PAID", "REJECTED"}:
                raise AppException(code=1001, message="提现状态不正确")
            statement = statement.where(WithdrawalOrder.status == normalized_status)
        if keyword:
            like = f"%{keyword.strip()}%"
            statement = statement.where(
                or_(
                    WithdrawalOrder.withdraw_no.like(like),
                    WithdrawalOrder.alipay_account.like(like),
                    User.mobile.like(like),
                    User.email.like(like),
                    User.uid.like(like),
                    User.nickname.like(like),
                )
            )

        total = self.db.execute(select(func.count()).select_from(statement.order_by(None).subquery())).scalar_one()
        rows = self.db.execute(statement.offset(params.offset).limit(params.page_size)).all()
        return AdminWithdrawalPageVO(
            pageNo=params.page_no,
            pageSize=params.page_size,
            total=total,
            hasMore=params.offset + len(rows) < total,
            records=[self._to_withdrawal_vo(order, user) for order, user in rows],
        )

    def update_withdrawal_status(
        self,
        withdraw_no: str,
        request_data: AdminWithdrawalStatusRequest,
        admin_user_id: int,
    ) -> AdminWithdrawalVO:
        target_status = request_data.status.strip().upper()
        if target_status not in {"PAID", "REJECTED"}:
            raise AppException(code=1001, message="提现状态只能标记为已打款或已驳回")

        self.db.commit()
        order = self.withdrawal_repo.get_by_withdraw_no(withdraw_no)
        if order is None:
            raise AppException(code=4004, message="提现单不存在", status_code=404)
        # Same inviter-first locking order as settlement and withdrawal reservation.
        self.db.scalar(select(User).where(User.id == order.user_id).with_for_update())
        order = self.db.scalar(select(WithdrawalOrder).where(WithdrawalOrder.withdraw_no == withdraw_no)
            .with_for_update().execution_options(populate_existing=True))
        if order.status == target_status:
            return self._to_withdrawal_vo(order, self.user_repo.get(order.user_id))
        if order.status != "PENDING":
            raise AppException(code=1001, message="只有待处理的提现单可以更新")
        if target_status == "PAID":
            from app.modules.invite.service import InviteService
            summary = InviteService(self.db)._build_withdrawal_summary(order.user_id, locked=True)
            if summary.debtAmount > 0:
                raise AppException(code=1001, message="返现余额因退款不足，请驳回申请后重新核算，暂不能标记打款")

        now = datetime.now()
        order.status = target_status
        order.handled_by = admin_user_id
        order.handled_at = now
        order.remark = request_data.remark.strip() if request_data.remark else _withdrawal_status_desc(target_status)
        if target_status == "PAID":
            order.paid_at = now
        self.db.commit()

        user = self.user_repo.get(order.user_id)
        return self._to_withdrawal_vo(order, user)

    def _to_user_vo(self, user: User, balance: tuple[int, int]) -> AdminUserVO:
        return AdminUserVO(
            uid=user.uid,
            mobile=user.mobile,
            email=user.email,
            nickname=user.nickname,
            inviteCode=user.invite_code,
            status=user.status,
            remainingPoints=sum(balance),
            localRemainingPoints=balance[0],
            purchasedRemainingPoints=balance[1],
            taskCount=self.task_repo.count_by_user_id(user.id),
            paidOrderCount=self._successful_order_count(user.id),
            createdAt=user.created_at,
        )

    def _to_user_detail_vo(self, user: User, balance: tuple[int, int] | None = None) -> AdminUserDetailVO:
        if balance is None:
            balance = self._quota_balances([user.id])[user.id]
        inviter_uid = None
        if user.inviter_id:
            inviter = self.user_repo.get(user.inviter_id)
            inviter_uid = inviter.uid if inviter else None
        return AdminUserDetailVO(
            uid=user.uid,
            mobile=user.mobile,
            email=user.email,
            nickname=user.nickname,
            inviteCode=user.invite_code,
            inviterUid=inviter_uid,
            remainingPoints=sum(balance),
            localRemainingPoints=balance[0],
            purchasedRemainingPoints=balance[1],
            vipExpireTime=user.vip_expire_time,
            taskCount=self.task_repo.count_by_user_id(user.id),
            paidOrderCount=self._successful_order_count(user.id),
            inviteCount=self.user_repo.count_by_inviter_id(user.id),
            status=user.status,
            createdAt=user.created_at,
        )

    def _to_withdrawal_vo(self, order: WithdrawalOrder, user: User | None) -> AdminWithdrawalVO:
        return AdminWithdrawalVO(
            withdrawNo=order.withdraw_no,
            userUid=user.uid if user else None,
            mobile=user.mobile if user else None,
            email=user.email if user else None,
            nickname=user.nickname if user else None,
            amount=self._normalize_decimal(order.amount),
            alipayAccount=order.alipay_account,
            status=order.status,
            statusDesc=_withdrawal_status_desc(order.status),
            remark=order.remark,
            handledBy=order.handled_by,
            createdAt=order.created_at,
            handledAt=order.handled_at,
            paidAt=order.paid_at,
        )

    def _get_user_by_uid_required(self, uid: str) -> User:
        user = self.user_repo.get_by_uid(uid)
        if user is None:
            raise AppException(code=4004, message="用户不存在", status_code=404)
        return user

    def _quota_balances(self, user_ids: list[int]) -> dict[int, tuple[int, int]]:
        if not user_ids:
            return {}
        purchased = dict.fromkeys(user_ids, 0)
        if get_settings().opcpay_enabled:
            self.db.commit()
            # Threads only perform HTTP queries. The SQLAlchemy session stays on this request's thread.
            with ThreadPoolExecutor(max_workers=4) as pool:
                purchased = dict(zip(user_ids, pool.map(QuotaService.load_purchased_points, user_ids)))
        local = {q.user_id: q.remaining_points or 0 for q in self.db.scalars(select(UserQuota).where(
            UserQuota.user_id.in_(user_ids), UserQuota.deleted == 0).execution_options(populate_existing=True))}
        return {uid: (local.get(uid, 0), purchased[uid]) for uid in user_ids}

    @staticmethod
    def _registered_condition():
        return ~select(GuestIdentity.user_id).where(GuestIdentity.user_id == User.id,
            GuestIdentity.state.in_(["GUEST", "MERGED", "EXPIRED"])).exists()

    @staticmethod
    def _new_registered_condition(start, end):
        from datetime import timezone
        from app.modules.admin.orders import CHINA_TZ
        no_identity = ~select(GuestIdentity.user_id).where(GuestIdentity.user_id == User.id).exists()
        lower = start.replace(tzinfo=CHINA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        upper = end.replace(tzinfo=CHINA_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        converted = select(GuestIdentity.user_id).where(GuestIdentity.user_id == User.id, GuestIdentity.state == "FORMAL",
            GuestIdentity.converted_at >= lower, GuestIdentity.converted_at <= upper).exists()
        return or_(and_(no_identity, User.created_at >= start, User.created_at <= end), converted)

    def _successful_order_count(self, user_id: int) -> int:
        from app.modules.admin.orders import AdminOrderService
        return AdminOrderService(self.db).successful_count(user_id)

    def _get_or_init_zero_quota(self, user_id: int) -> UserQuota:
        quota = self.quota_repo.get_by_user_id(user_id)
        if quota is not None:
            return quota
        quota = UserQuota(user_id=user_id, remaining_points=0, daily_free_used=0, status="ENABLE")
        self.quota_repo.add(quota)
        return quota

    def _count(self, model, *conditions) -> int:
        statement = select(func.count()).select_from(model).where(model.deleted == 0)
        if conditions:
            statement = statement.where(and_(*conditions))
        return self.db.execute(statement).scalar_one()

    def _sum_decimal(self, statement) -> Decimal:
        return self._normalize_decimal(self.db.execute(statement).scalar_one())

    def _normalize_decimal(self, amount) -> Decimal:
        return Decimal(amount or ZERO).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    def _generate_admin_biz_no(self) -> str:
        return f"ADMIN{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"


def _withdrawal_status_desc(status: str) -> str:
    return {
        "PENDING": "待处理",
        "PAID": "已打款",
        "REJECTED": "已驳回",
    }.get(status, status)
