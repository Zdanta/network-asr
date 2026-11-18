from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.modules.quota.schemas import QuotaInfoVO, QuotaLogPageVO
from app.modules.quota.service import QuotaService

router = APIRouter()


def _load_user(db: Session, current_user: CurrentUser) -> User:
    user = UserRepository(db).get(current_user.id)
    if user is None:
        raise AppException(code=1002, message="登录状态已失效，请重新登录", status_code=401)
    return user


@router.get("", response_model=ApiResponse[QuotaInfoVO])
def get_quota(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[QuotaInfoVO]:
    user = _load_user(db, current_user)
    return success_response(QuotaService(db).get_quota_info(user))


@router.get("/logs", response_model=ApiResponse[QuotaLogPageVO])
def get_quota_logs(
    change_type: str | None = Query(default=None, alias="changeType"),
    page_no: int = Query(default=1, ge=1, alias="pageNo"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[QuotaLogPageVO]:
    data = QuotaService(db).list_quota_logs(current_user.id, change_type, page_no, page_size)
    return success_response(data)
