from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class InviteInfoVO(BaseModel):
    inviteCode: str
    inviteCount: int
    rewardTotal: Decimal
    rewardRatePercent: int = 10
    holdDays: int = 7


class InviteRecordVO(BaseModel):
    inviteeUid: str
    rewardType: str
    rewardValue: int
    rechargeAmount: Decimal
    rewardAmount: Decimal
    rewardStatus: str
    triggerOrderNo: str | None = None
    createdAt: datetime | None = None


class WithdrawalSummaryVO(BaseModel):
    rewardTotal: Decimal
    pendingAmount: Decimal
    paidAmount: Decimal
    withdrawableAmount: Decimal
    minWithdrawalAmount: Decimal
    canApply: bool
    frozenRewardAmount: Decimal = Decimal("0.00")
    debtAmount: Decimal = Decimal("0.00")


class WithdrawalRecordVO(BaseModel):
    withdrawNo: str
    amount: Decimal
    alipayAccount: str
    status: str
    statusDesc: str
    remark: str | None = None
    createdAt: datetime | None = None
    handledAt: datetime | None = None
    paidAt: datetime | None = None


class WithdrawalApplyRequest(BaseModel):
    alipayAccount: str = Field(min_length=1, max_length=128)
