from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user
from app.modules.quota.schemas import QuotaLogPageVO
from app.modules.quota.service import QuotaService

router = APIRouter()


@router.get("/quota-logs", response_model=ApiResponse[QuotaLogPageVO])
def get_profile_quota_logs(
    change_type: str | None = Query(default=None, alias="changeType"),
    page_no: int = Query(default=1, ge=1, alias="pageNo"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[QuotaLogPageVO]:
    data = QuotaService(db).list_quota_logs(current_user.id, change_type, page_no, page_size)
    return success_response(data)
