from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.response import success_response, ApiResponse
from app.core.security import get_current_user, CurrentUser
from app.models.user import User
from app.modules.user.service import UserService
from app.modules.user.schemas import UserInfoVO
from app.modules.guest.service import GuestService, COOKIE, client_ip
from app.modules.payment.opcpay_service import OpcpayService
from app.modules.payment.opcpay_router import CatalogVO

router = APIRouter()


class ClaimRequest(BaseModel):
    deviceId: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")


@router.get("/public/experience")
def experience(db: Session = Depends(get_db)):
    from app.modules.quota.service import QuotaService
    policy = GuestService(db).policy()
    return success_response({"enabled": policy["enabled"], "points": policy["points"],
        "secondsPerPoint": QuotaService(db).load_seconds_per_point(), "uploadMb": policy["upload_mb"], "sessionDays": policy["session_days"]})


@router.get("/public/catalog", response_model=ApiResponse[CatalogVO])
def public_catalog(db: Session = Depends(get_db)):
    return success_response(OpcpayService(db).catalog())


@router.get("/auth/guest-session", response_model=ApiResponse[UserInfoVO | None])
def guest_session(request: Request, db: Session = Depends(get_db)):
    identity = GuestService(db).from_cookie(request.cookies.get(COOKIE))
    if not identity:
        return success_response(None)
    user = db.get(User, identity.user_id)
    if not user or user.deleted or user.status != "ENABLE":
        return success_response(None)
    return success_response(UserService(db).get_user_info(user))


@router.post("/auth/guest", response_model=ApiResponse[UserInfoVO])
def claim(body: ClaimRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    # A logged-in visitor must never accidentally replace their real account with a guest.
    if request.headers.get("satoken") or request.headers.get("authorization"):
        user = get_current_user(request, db)
        return success_response(UserService(db).get_user_info(db.get(User, user.id)))
    service = GuestService(db)
    user_id, secret = service.claim(body.deviceId, request.cookies.get(COOKIE), client_ip(request))
    if secret:
        response.set_cookie(COOKIE, secret, max_age=service.policy()["session_days"] * 86400,
            httponly=True, secure=get_settings().app_env == "production" or request.url.scheme == "https", samesite="lax", path="/")
    return success_response(UserService(db).get_user_info(db.get(User, user_id)))
