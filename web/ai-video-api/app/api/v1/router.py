from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.profile.router import router as profile_router
from app.modules.quota.router import router as quota_router
from app.modules.system.router import router as system_router
from app.modules.file.router import router as file_router
from app.modules.invite.router import router as invite_router
from app.modules.media_import.router import router as media_import_router
from app.modules.payment.router import router as payment_router
from app.modules.payment.opcpay_router import router as opcpay_router
from app.modules.task.router import router as task_router
from app.modules.user.router import router as user_router


api_v1_router = APIRouter()
from app.modules.guest.router import router as guest_router
api_v1_router.include_router(guest_router, tags=["guest"])
from app.modules.guest.admin import router as guest_admin_router
api_v1_router.include_router(guest_admin_router, prefix="/admin", tags=["admin-guest"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(user_router, prefix="/user", tags=["user"])
api_v1_router.include_router(quota_router, prefix="/quota", tags=["quota"])
api_v1_router.include_router(file_router, prefix="/file", tags=["file"])
api_v1_router.include_router(media_import_router, prefix="/file/import-link", tags=["file-import"])
api_v1_router.include_router(task_router, prefix="/task", tags=["task"])
api_v1_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_v1_router.include_router(opcpay_router, prefix="/payment/opcpay", tags=["opcpay"])
api_v1_router.include_router(invite_router, prefix="/invite", tags=["invite"])
api_v1_router.include_router(profile_router, prefix="/profile", tags=["profile"])
api_v1_router.include_router(system_router, prefix="/system", tags=["system"])
