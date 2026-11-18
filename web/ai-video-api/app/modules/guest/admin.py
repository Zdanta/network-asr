from app.common.clock import utc_naive_now
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.response import success_response
from app.modules.admin.dependencies import get_admin_user
from app.core.security import CurrentUser
from app.models.guest import GuestIdentity, GuestReservation
from app.models.quota import UserQuota
from app.models.system import SysConfig
from app.models.task import Task
from app.modules.guest.service import GuestService, POLICY

router = APIRouter()


class GuestPolicyRequest(BaseModel):
    enabled: bool
    points: int = Field(ge=1, le=1000)
    ip_points: int = Field(ge=1, le=100000)
    global_points: int = Field(ge=1, le=1000000)
    ip_claims: int = Field(ge=1, le=100)
    upload_mb: int = Field(ge=1, le=100)
    session_days: int = Field(ge=1, le=30)


@router.get("/guest-policy")
def policy(_: CurrentUser = Depends(get_admin_user), db: Session = Depends(get_db)):
    return success_response(GuestService(db).policy())


@router.put("/guest-policy")
def update_policy(body: GuestPolicyRequest, _: CurrentUser = Depends(get_admin_user), db: Session = Depends(get_db)):
    GuestService(db).lock()
    for name, value in body.model_dump().items():
        key = "GUEST_" + name.upper()
        row = db.scalar(select(SysConfig).where(SysConfig.config_key == key).with_for_update())
        if not row:
            row = SysConfig(config_key=key, config_name="访客体验设置", config_value=str(value), status="ENABLE")
            db.add(row)
        row.config_value = str(value).lower()
    db.commit()
    return success_response(GuestService(db).policy())


@router.get("/guests")
def guests(pageNo: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
           _: CurrentUser = Depends(get_admin_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(GuestIdentity)) or 0
    rows = db.execute(select(GuestIdentity, UserQuota.remaining_points).outerjoin(UserQuota, UserQuota.user_id == GuestIdentity.user_id)
        .order_by(GuestIdentity.created_at.desc(), GuestIdentity.user_id.desc()).offset((pageNo-1)*pageSize).limit(pageSize)).all()
    converted = db.scalar(select(func.count()).select_from(GuestIdentity).where(GuestIdentity.state.in_(["FORMAL", "MERGED"]))) or 0
    successful = db.scalar(select(func.count()).select_from(GuestReservation).join(Task, Task.task_no == GuestReservation.task_no)
                          .where(Task.status == "SUCCESS")) or 0
    started = db.scalar(select(func.count()).select_from(GuestReservation)) or 0
    from app.modules.admin.orders import order_projection
    orders = order_projection()
    converted_local = func.timestampadd(text("HOUR"), 8, GuestIdentity.converted_at) if db.bind.dialect.name == "mysql" else func.datetime(GuestIdentity.converted_at, "+8 hours")
    paid = db.scalar(select(func.count(func.distinct(GuestIdentity.user_id))).select_from(GuestIdentity).join(orders,
        orders.c.user_id == func.coalesce(GuestIdentity.target_user_id, GuestIdentity.user_id)).where(
            GuestIdentity.converted_at.is_not(None), orders.c.status == "PAID",
            orders.c.created_at >= converted_local)) or 0
    since = utc_naive_now() - timedelta(hours=24)
    used = db.scalar(select(func.coalesce(func.sum(GuestReservation.points), 0)).where(GuestReservation.created_at >= since,
                      GuestReservation.state.in_(["RESERVED", "CONSUMED"]))) or 0
    return success_response({"total": total, "converted": converted, "startedTasks": started, "successfulTasks": successful,
        "payingVisitors": paid, "reservedAndUsed24h": used, "pageNo":pageNo, "pageSize":pageSize,
        "hasMore":pageNo*pageSize < total, "records":[{"userId":g.user_id,"state":g.state,"remainingPoints":points or 0,
            "initialPoints":g.initial_points,"network":g.ip_hash[:10],"createdAt":g.created_at.isoformat()+"Z",
            "convertedAt":g.converted_at.isoformat()+"Z" if g.converted_at else None} for g,points in rows]})
