from datetime import datetime

from pydantic import BaseModel


class QuotaInfoVO(BaseModel):
    remainingPoints: int
    remainingCount: int
    localRemainingPoints: int = 0
    purchasedRemainingPoints: int = 0
    vip: bool
    vipExpireTime: datetime | None = None
    secondsPerPoint: int
    pointsPerMinute: int


class QuotaLogVO(BaseModel):
    changeType: str
    changeTypeDesc: str
    changeAmount: int
    afterPoints: int | None = None
    bizNo: str | None = None
    remark: str | None = None
    createdAt: str


class QuotaLogPageVO(BaseModel):
    records: list[QuotaLogVO]
    total: int
    pageNo: int
    pageSize: int
    pages: int
