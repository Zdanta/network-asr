import secrets
from decimal import Decimal, ROUND_DOWN

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.user import User

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.invite import InviteRecord
from app.models.payment import PayOrder
from app.models.withdrawal import WithdrawalOrder
from app.modules.invite.schemas import (
    InviteInfoVO,
    InviteRecordVO,
    WithdrawalRecordVO,
    WithdrawalSummaryVO,
)
from app.repositories.invite import InviteRecordRepository
from app.repositories.system import SysConfigRepository
from app.repositories.user import UserRepository
from app.repositories.withdrawal import WithdrawalOrderRepository

ZERO = Decimal("0.00")


class InviteService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.invite_repo = InviteRecordRepository(db)
        self.user_repo = UserRepository(db)
        self.withdrawal_repo = WithdrawalOrderRepository(db)
        self.config_repo = SysConfigRepository(db)

    def get_invite_info(self, user_id: int) -> InviteInfoVO:
        user = self.user_repo.get(user_id)
        if user is None:
            raise AppException(code=4004, message="用户不存在", status_code=404)
        return InviteInfoVO(
            inviteCode=user.invite_code,
            inviteCount=self.user_repo.count_by_inviter_id(user_id),
            rewardTotal=self._normalize(self.invite_repo.sum_success_reward_amount(user_id)),
            rewardRatePercent=self._invite_reward_rate_percent(),
            holdDays=get_settings().invite_reward_hold_days,
        )

    def list_invite_records(self, user_id: int) -> list[InviteRecordVO]:
        records = self.invite_repo.list_by_inviter_id(user_id)
        users = self.user_repo.list_by_ids(list({item.invitee_id for item in records}))
        uid_map = {user.id: user.uid for user in users}
        return [
            InviteRecordVO(
                inviteeUid=uid_map.get(item.invitee_id, ""),
                rewardType=item.reward_type,
                rewardValue=item.reward_value,
                rechargeAmount=self._normalize(item.recharge_amount),
                rewardAmount=self._normalize(item.reward_amount),
                rewardStatus=item.reward_status,
                triggerOrderNo=item.trigger_order_no,
                createdAt=item.created_at,
            )
            for item in records
        ]

    def handle_paid_reward(self, pay_order: PayOrder) -> bool:
        if pay_order.status != "SUCCESS":
            return False

        invitee = self.user_repo.get(pay_order.user_id)
        if invitee is None or invitee.inviter_id is None:
            return False

        self.db.scalar(select(User).where(User.id == invitee.inviter_id).with_for_update())
        existing = self.db.scalar(select(InviteRecord).where(InviteRecord.trigger_order_no == pay_order.order_no)
                                  .with_for_update().execution_options(populate_existing=True))
        if existing is not None and existing.reward_status == "SUCCESS":
            return False

        reward_amount = self._calculate_reward_amount(pay_order.amount)
        if reward_amount <= ZERO:
            return False

        if existing is None:
            existing = InviteRecord(
                inviter_id=invitee.inviter_id,
                invitee_id=invitee.id,
                reward_type="CASH",
                reward_value=0,
                recharge_amount=pay_order.amount,
                reward_amount=reward_amount,
                reward_status="PENDING",
                trigger_order_no=pay_order.order_no,
                remark="邀请返现待确认",
            )
            self.invite_repo.add(existing)

        existing.recharge_amount = pay_order.amount
        existing.reward_amount = reward_amount
        existing.reward_status = "SUCCESS"
        existing.remark = "邀请返现已记录"
        return True

    def get_withdrawal_summary(self, user_id: int) -> WithdrawalSummaryVO:
        return self._build_withdrawal_summary(user_id)

    def list_withdrawals(self, user_id: int) -> list[WithdrawalRecordVO]:
        return [self._to_withdrawal_vo(item) for item in self.withdrawal_repo.list_by_user_id(user_id)]

    def apply_withdrawal(self, user_id: int, alipay_account: str) -> WithdrawalRecordVO:
        normalized_account = (alipay_account or "").strip()
        if not normalized_account:
            raise AppException(code=1001, message="请填写支付宝账号")

        self.db.commit()
        user = self.db.scalar(select(User).where(User.id == user_id, User.deleted == 0).with_for_update())
        if user is None or user.status != "ENABLE":
            raise AppException(code=1003, message="账号不可用", status_code=403)
        summary = self._build_withdrawal_summary(user_id, locked=True)
        if summary.withdrawableAmount < summary.minWithdrawalAmount:
            raise AppException(code=1001, message=f"满 ¥{summary.minWithdrawalAmount} 后才可提现")

        order = WithdrawalOrder(
            withdraw_no=self._generate_withdraw_no(),
            user_id=user_id,
            amount=summary.withdrawableAmount,
            alipay_account=normalized_account,
            status="PENDING",
            remark="等待人工打款",
        )
        self.withdrawal_repo.add(order)
        self.db.commit()
        return self._to_withdrawal_vo(order)

    def _build_withdrawal_summary(self, user_id: int, locked: bool = False) -> WithdrawalSummaryVO:
        reward_total = self._normalize(self.invite_repo.sum_success_reward_amount(user_id))
        pending_amount = self._normalize(self.withdrawal_repo.sum_amount_by_status(user_id, "PENDING"))
        paid_amount = self._normalize(self.withdrawal_repo.sum_amount_by_status(user_id, "PAID"))
        if locked:
            rewards = list(self.db.execute(select(InviteRecord.reward_amount, InviteRecord.reward_status)
                .where(InviteRecord.inviter_id == user_id, InviteRecord.deleted == 0).with_for_update()))
            withdrawals = list(self.db.execute(select(WithdrawalOrder.amount, WithdrawalOrder.status)
                .where(WithdrawalOrder.user_id == user_id, WithdrawalOrder.deleted == 0).with_for_update()))
            reward_total = self._normalize(sum((amount for amount, status in rewards if status == "SUCCESS"), ZERO))
            pending_amount = self._normalize(sum((amount for amount, status in withdrawals if status == "PENDING"), ZERO))
            paid_amount = self._normalize(sum((amount for amount, status in withdrawals if status == "PAID"), ZERO))
        withdrawable_amount = max(reward_total - pending_amount - paid_amount, ZERO)
        min_amount = self._min_withdrawal_amount()
        return WithdrawalSummaryVO(
            rewardTotal=reward_total,
            pendingAmount=pending_amount,
            paidAmount=paid_amount,
            withdrawableAmount=self._normalize(withdrawable_amount),
            minWithdrawalAmount=min_amount,
            canApply=withdrawable_amount >= min_amount,
            frozenRewardAmount=self._normalize(self.db.scalar(select(func.coalesce(func.sum(InviteRecord.reward_amount), 0))
                .where(InviteRecord.inviter_id == user_id, InviteRecord.deleted == 0, InviteRecord.reward_status == "PENDING"))),
            debtAmount=max(pending_amount + paid_amount - reward_total, ZERO),
        )

    def _calculate_reward_amount(self, amount: Decimal) -> Decimal:
        rate = Decimal(self._invite_reward_rate_percent())
        return self._normalize(Decimal(amount or ZERO) * rate / Decimal("100"))

    def _invite_reward_rate_percent(self) -> int:
        config = self.config_repo.get_by_key("INVITE_REWARD_RATE_PERCENT")
        if config is not None and config.config_value:
            try:
                value = int(config.config_value)
                if value >= 0:
                    return min(value, 100)
            except ValueError:
                pass
        return get_settings().invite_reward_rate_percent

    def _min_withdrawal_amount(self) -> Decimal:
        config = self.config_repo.get_by_key("MIN_WITHDRAWAL_AMOUNT")
        if config is not None and config.config_value:
            try:
                return self._normalize(Decimal(config.config_value))
            except Exception:
                pass
        return self._normalize(Decimal(get_settings().min_withdrawal_amount))

    def _generate_withdraw_no(self) -> str:
        for _ in range(10):
            withdraw_no = f"WD{secrets.token_hex(9).upper()}"
            if self.withdrawal_repo.get_by_withdraw_no(withdraw_no) is None:
                return withdraw_no
        raise AppException(code=5000, message="提现单号生成失败，请稍后重试", status_code=500)

    def _to_withdrawal_vo(self, order: WithdrawalOrder) -> WithdrawalRecordVO:
        return WithdrawalRecordVO(
            withdrawNo=order.withdraw_no,
            amount=self._normalize(order.amount),
            alipayAccount=order.alipay_account,
            status=order.status,
            statusDesc=_withdrawal_status_desc(order.status),
            remark=order.remark,
            createdAt=order.created_at,
            handledAt=order.handled_at,
            paidAt=order.paid_at,
        )

    def _normalize(self, amount) -> Decimal:
        return Decimal(amount or ZERO).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _withdrawal_status_desc(status: str) -> str:
    return {
        "PENDING": "待处理",
        "PAID": "已打款",
        "REJECTED": "已驳回",
    }.get(status, status)
