from fastapi import Depends

from app.core.exceptions import AppException
from app.core.security import CurrentUser, get_current_user


def get_admin_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise AppException(code=1003, message="需要管理员权限", status_code=403)
    return current_user
