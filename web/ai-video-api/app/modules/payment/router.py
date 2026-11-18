from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_registered_user
from app.modules.payment.schemas import (
    PayNotifyRequest,
    PayNotifyVO,
    PayOrderCreateRequest,
    PayOrderCreateVO,
    PayOrderInfoVO,
)
from app.modules.payment.service import PaymentService

router = APIRouter()


@router.post("/order", response_model=ApiResponse[PayOrderCreateVO])
def create_order(
    request_data: PayOrderCreateRequest,
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PayOrderCreateVO]:
    data = PaymentService(db).create_order(current_user.id, request_data)
    return success_response(data)


@router.get("/order/{order_no}", response_model=ApiResponse[PayOrderInfoVO])
def get_order(
    order_no: str,
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PayOrderInfoVO]:
    data = PaymentService(db).get_order(current_user.id, order_no)
    return success_response(data)


@router.post("/notify", response_model=ApiResponse[PayNotifyVO])
def payment_notify(
    request_data: PayNotifyRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[PayNotifyVO]:
    data = PaymentService(db).handle_notify(request_data)
    return success_response(data)


@router.post("/notify/wechat", response_model=ApiResponse[PayNotifyVO])
def wechat_payment_notify(
    request_data: PayNotifyRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[PayNotifyVO]:
    data = PaymentService(db).handle_wechat_notify(request_data)
    return success_response(data)
