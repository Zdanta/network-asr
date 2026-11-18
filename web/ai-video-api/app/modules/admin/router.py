from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser
from app.modules.admin.dependencies import get_admin_user
from app.modules.admin.schemas import (
    AdminDashboardOverviewVO,
    AdminQuotaAdjustRequest,
    AdminUserDetailVO,
    AdminUserPageVO,
    AdminWithdrawalPageVO,
    AdminWithdrawalStatusRequest,
    AdminWithdrawalVO,
)
from app.modules.admin.service import AdminService
from app.modules.admin.orders import AdminOrderService
from app.modules.admin.schemas import AdminOrderPageVO

router = APIRouter()


@router.get("/orders", response_model=ApiResponse[AdminOrderPageVO])
def list_orders(
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page_no: int = Query(default=1, ge=1, alias="pageNo"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminOrderPageVO]:
    return success_response(AdminOrderService(db).list_orders(keyword, status, source, page_no, page_size))


@router.get("/dashboard/overview", response_model=ApiResponse[AdminDashboardOverviewVO])
def dashboard_overview(
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminDashboardOverviewVO]:
    data = AdminService(db).get_dashboard_overview()
    return success_response(data)


@router.get("/users", response_model=ApiResponse[AdminUserPageVO])
def list_users(
    keyword: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="pageNo"),
    page_size: int = Query(default=10, alias="pageSize"),
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminUserPageVO]:
    data = AdminService(db).list_users(keyword, page_no, page_size)
    return success_response(data)


@router.get("/users/{uid}", response_model=ApiResponse[AdminUserDetailVO])
def get_user_detail(
    uid: str,
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminUserDetailVO]:
    data = AdminService(db).get_user_detail(uid)
    return success_response(data)


@router.post("/users/quota/adjust", response_model=ApiResponse[AdminUserDetailVO])
def adjust_user_quota(
    request_data: AdminQuotaAdjustRequest,
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminUserDetailVO]:
    data = AdminService(db).adjust_user_quota(request_data)
    return success_response(data)


@router.get("/withdrawals", response_model=ApiResponse[AdminWithdrawalPageVO])
def list_withdrawals(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page_no: int = Query(default=1, alias="pageNo"),
    page_size: int = Query(default=10, alias="pageSize"),
    _: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminWithdrawalPageVO]:
    data = AdminService(db).list_withdrawals(status, keyword, page_no, page_size)
    return success_response(data)


@router.put("/withdrawals/{withdrawNo}/status", response_model=ApiResponse[AdminWithdrawalVO])
def update_withdrawal_status(
    request_data: AdminWithdrawalStatusRequest,
    withdraw_no: str = Path(alias="withdrawNo"),
    current_user: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminWithdrawalVO]:
    data = AdminService(db).update_withdrawal_status(withdraw_no, request_data, current_user.id)
    return success_response(data)
