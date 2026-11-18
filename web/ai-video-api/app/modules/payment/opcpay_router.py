from fastapi import APIRouter, Depends
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_registered_user
from app.modules.payment.opcpay_service import OpcpayService

router = APIRouter()


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actionId: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    skuId: str = Field(min_length=1, max_length=128)


class PlanVO(BaseModel):
    skuId: str
    name: str
    price: str
    quantity: int


class CatalogVO(BaseModel):
    enabled: bool
    billingMode: str | None = None
    quotaUnit: Literal["POINT", "COUNT"] | None = None
    transactionQuery: bool = False
    plans: list[PlanVO]


class AccessVO(BaseModel):
    remaining: int
    quotaUnit: str | None
    accessGranted: bool
    legacyRemainingPoints: int


class PurchaseVO(BaseModel):
    orderNo: str
    status: Literal["READY", "FAILED", "UNKNOWN"]
    payUrl: str | None
    qrCode: str | None = None
    expiresAt: str | None = None


class TransactionVO(BaseModel):
    status: Literal["PAID", "PENDING", "REFUNDED", "UNKNOWN"]
    checkedAt: str | None


@router.get("/catalog", response_model=ApiResponse[CatalogVO])
def catalog(user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    return success_response(OpcpayService(db).catalog(user.id))


@router.get("/access", response_model=ApiResponse[AccessVO])
def access(user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    service = OpcpayService(db)
    service.require_enabled()
    data = service.client.access(user.id)
    from app.modules.quota.service import QuotaService
    legacy = QuotaService(db).get_or_init_quota(user.id)
    return success_response({"remaining": data.get("remaining", 0), "quotaUnit": data.get("quota_unit"),
                             "accessGranted": data.get("access_granted") is True,
                             "legacyRemainingPoints": legacy.remaining_points})


@router.post("/purchase", response_model=ApiResponse[PurchaseVO])
def purchase(body: PurchaseRequest, user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    return success_response(OpcpayService(db).purchase(user.id, body.actionId, body.skuId))


@router.get("/purchase/{order_no}", response_model=ApiResponse[TransactionVO])
def transaction(order_no: str, user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    return success_response(OpcpayService(db).transaction(user.id, order_no))


@router.get("/purchase/{order_no}/entry", response_model=ApiResponse[PurchaseVO])
def entry(order_no: str, user: CurrentUser = Depends(get_registered_user), db: Session = Depends(get_db)):
    return success_response(OpcpayService(db).entry(user.id, order_no))
