from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        return str(value).strip().lower()


class BindEmailRequest(EmailRequest):
    code: str = Field(pattern=r"^\d{6}$")


class LoginRequest(BindEmailRequest):
    inviteCode: str | None = None


class LoginVO(BaseModel):
    guestConverted: bool = False
    token: str
    uid: str
    userId: int
    mobile: str | None = None
    email: str | None = None
    nickname: str | None = None
    inviteCode: str
    vipExpireTime: datetime | None = None
    remainingPoints: int
    admin: bool = False


class LogoutVO(BaseModel):
    loggedOut: bool = True
