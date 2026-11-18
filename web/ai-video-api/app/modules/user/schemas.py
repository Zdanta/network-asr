from datetime import datetime

from pydantic import BaseModel


class UserInfoVO(BaseModel):
    uid: str
    userId: int
    mobile: str | None = None
    email: str | None = None
    nickname: str | None = None
    inviteCode: str
    vipExpireTime: datetime | None = None
    remainingPoints: int
    remainingCount: int
    admin: bool = False
    guest: bool = False
