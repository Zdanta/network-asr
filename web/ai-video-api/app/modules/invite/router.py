from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_registered_user
from app.modules.invite.schemas import (
    InviteInfoVO,
    InviteRecordVO,
    WithdrawalApplyRequest,
    WithdrawalRecordVO,
    WithdrawalSummaryVO,
)
from app.modules.invite.service import InviteService

router = APIRouter()


@router.get("", response_model=ApiResponse[InviteInfoVO])
def get_invite_info(
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[InviteInfoVO]:
    data = InviteService(db).get_invite_info(current_user.id)
    return success_response(data)


@router.get("/records", response_model=ApiResponse[list[InviteRecordVO]])
def list_invite_records(
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[InviteRecordVO]]:
    data = InviteService(db).list_invite_records(current_user.id)
    return success_response(data)


@router.get("/withdrawals/summary", response_model=ApiResponse[WithdrawalSummaryVO])
def get_withdrawal_summary(
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[WithdrawalSummaryVO]:
    data = InviteService(db).get_withdrawal_summary(current_user.id)
    return success_response(data)


@router.get("/withdrawals", response_model=ApiResponse[list[WithdrawalRecordVO]])
def list_withdrawals(
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[WithdrawalRecordVO]]:
    data = InviteService(db).list_withdrawals(current_user.id)
    return success_response(data)


@router.post("/withdrawals", response_model=ApiResponse[WithdrawalRecordVO])
def apply_withdrawal(
    request_data: WithdrawalApplyRequest,
    current_user: CurrentUser = Depends(get_registered_user),
    db: Session = Depends(get_db),
) -> ApiResponse[WithdrawalRecordVO]:
    data = InviteService(db).apply_withdrawal(current_user.id, request_data.alipayAccount)
    return success_response(data)
