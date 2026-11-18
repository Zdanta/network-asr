from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AdminDashboardOverviewVO(BaseModel):
    totalUsers: int
    todayNewUsers: int
    todayTasks: int
    todaySuccessTasks: int
    todayFailTasks: int
    todayPaidOrders: int
    todayPaidAmount: Decimal
    pendingFailTasks: int
    pendingWithdrawals: int = 0
    pendingWithdrawalAmount: Decimal = Decimal("0.00")


class AdminOrderVO(BaseModel):
    source: str
    orderNo: str
    userUid: str | None = None
    email: str | None = None
    nickname: str | None = None
    productName: str
    amount: Decimal | None = None
    quantity: int | None = None
    status: str
    channel: str
    createdAt: datetime
    paymentConfirmedAt: datetime | None = None
    checkedAt: datetime | None = None


class AdminOrderPageVO(BaseModel):
    records: list[AdminOrderVO]
    total: int
    pageNo: int
    pageSize: int
    hasMore: bool


class AdminUserVO(BaseModel):
    uid: str
    mobile: str | None = None
    email: str | None = None
    nickname: str | None = None
    inviteCode: str
    status: str
    remainingPoints: int
    localRemainingPoints: int = 0
    purchasedRemainingPoints: int = 0
    taskCount: int
    paidOrderCount: int
    createdAt: datetime | None = None


class AdminUserPageVO(BaseModel):
    pageNo: int
    pageSize: int
    total: int
    hasMore: bool
    records: list[AdminUserVO]


class AdminUserDetailVO(BaseModel):
    uid: str
    mobile: str | None = None
    email: str | None = None
    nickname: str | None = None
    inviteCode: str
    inviterUid: str | None = None
    remainingPoints: int
    localRemainingPoints: int = 0
    purchasedRemainingPoints: int = 0
    vipExpireTime: datetime | None = None
    taskCount: int
    paidOrderCount: int
    inviteCount: int
    status: str
    createdAt: datetime | None = None


class AdminQuotaAdjustRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=64)
    points: int
    remark: str = Field(min_length=1, max_length=255)


class AdminWithdrawalVO(BaseModel):
    withdrawNo: str
    userUid: str | None = None
    mobile: str | None = None
    email: str | None = None
    nickname: str | None = None
    amount: Decimal
    alipayAccount: str
    status: str
    statusDesc: str
    remark: str | None = None
    handledBy: int | None = None
    createdAt: datetime | None = None
    handledAt: datetime | None = None
    paidAt: datetime | None = None


class AdminWithdrawalPageVO(BaseModel):
    pageNo: int
    pageSize: int
    total: int
    hasMore: bool
    records: list[AdminWithdrawalVO]


class AdminWithdrawalStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    remark: str | None = Field(default=None, max_length=255)
