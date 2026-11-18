from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PayOrderCreateRequest(BaseModel):
    productType: str = Field(min_length=1, max_length=32)


class PayOrderCreateVO(BaseModel):
    orderNo: str
    productType: str
    productName: str
    amount: Decimal
    status: str
    payUrl: str
    qrCode: str


class PayOrderInfoVO(BaseModel):
    orderNo: str
    productType: str
    amount: Decimal
    status: str
    paidAt: datetime | None = None


class PayNotifyRequest(BaseModel):
    orderNo: str | None = None
    thirdPartyOrderNo: str | None = None
    amount: Decimal | None = None
    payChannel: str | None = None
    payStatus: str | None = None
    sign: str | None = None
    notifyBody: str | None = None
    wechatTimestamp: str | None = None
    wechatNonce: str | None = None
    wechatSerial: str | None = None
    wechatSignature: str | None = None


class PayNotifyVO(BaseModel):
    orderNo: str | None = None
    status: str
