from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.core.security import CurrentUser, get_current_user
from app.repositories.user import UserRepository
from app.modules.user.schemas import UserInfoVO
from app.modules.user.service import UserService

router = APIRouter()


@router.get("/info", response_model=ApiResponse[UserInfoVO])
def get_user_info(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[UserInfoVO]:
    user = UserRepository(db).get(current_user.id)
    if user is None:
        raise AppException(code=1002, message="登录状态已失效，请重新登录", status_code=401)
    return success_response(UserService(db).get_user_info(user))
