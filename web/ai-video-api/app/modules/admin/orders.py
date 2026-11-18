"""Read-only order projection shared by admin lists, user counts and dashboard totals."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Integer, Numeric, String, case, cast, func, literal, or_, select, type_coerce, union_all

from app.common.pagination import PageParams
from app.core.exceptions import AppException
from app.models.opcpay import OpcpayOperation
from app.models.payment import PayOrder
from app.models.user import User
from app.modules.admin.schemas import AdminOrderPageVO, AdminOrderVO

CHINA_TZ = timezone(timedelta(hours=8))
STATUSES = {"PAID", "PENDING", "FAILED", "CLOSED", "REFUNDED", "UNKNOWN"}


def order_projection():
    meta = type_coerce(OpcpayOperation.metadata_json, JSON)
    response = type_coerce(OpcpayOperation.response_json, JSON)
    observed = meta["payment_status"].as_string()
    checked = meta["checked_at"].as_string()
    verified = observed.in_(["PAID", "REFUNDED"]) & checked.is_not(None)
    first_paid = meta["paid_confirmed_at"].as_string()
    # checked_at is the historical fallback; never call this the actual Alipay payment time.
    paid_confirmed = case((verified & (observed == "PAID"), func.coalesce(first_paid, checked)), else_=first_paid)
    same_provider = select(OpcpayOperation.id).where(OpcpayOperation.kind == "PURCHASE", OpcpayOperation.deleted == 0,
        OpcpayOperation.user_id == PayOrder.user_id, OpcpayOperation.biz_no == PayOrder.order_no, verified).correlate(PayOrder).exists()
    same_legacy = select(PayOrder.id).where(PayOrder.deleted == 0, PayOrder.user_id == OpcpayOperation.user_id,
        PayOrder.order_no == OpcpayOperation.biz_no).correlate(OpcpayOperation).exists()
    legacy_amount = select(PayOrder.amount).where(PayOrder.deleted == 0, PayOrder.user_id == OpcpayOperation.user_id,
        PayOrder.order_no == OpcpayOperation.biz_no).correlate(OpcpayOperation).scalar_subquery()
    legacy_status = case((PayOrder.status == "SUCCESS", "PAID"),
        (PayOrder.status.in_(["INIT", "PAYING", "PENDING"]), "PENDING"),
        (PayOrder.status.in_(["FAIL", "FAILED"]), "FAILED"),
        (PayOrder.status.in_(["CLOSE", "CLOSED"]), "CLOSED"),
        (PayOrder.status == "REFUNDED", "REFUNDED"), else_="UNKNOWN")
    legacy = select(literal("LEGACY").label("source"), PayOrder.order_no.label("order_no"), PayOrder.user_id.label("user_id"),
        PayOrder.product_name.label("product_name"), PayOrder.amount.label("amount"), literal(None, Integer).label("quantity"),
        legacy_status.label("status"), PayOrder.pay_channel.label("channel"), PayOrder.created_at.label("created_at"),
        cast(PayOrder.paid_at, String).label("confirmed_at"), literal(None, String).label("checked_at")).where(
            PayOrder.deleted == 0, ~same_provider)
    provider_status = case((verified, observed),
        (observed.in_(["PAID", "REFUNDED"]), "UNKNOWN"),
        (response["status"].as_string() == "READY", "PENDING"),
        (or_(OpcpayOperation.state == "FAILED", response["status"].as_string() == "FAILED"), "FAILED"), else_="UNKNOWN")
    provider = select(literal("OPCPAY").label("source"), OpcpayOperation.biz_no.label("order_no"),
        OpcpayOperation.user_id.label("user_id"), func.coalesce(meta["name"].as_string(), "资源包").label("product_name"),
        func.coalesce(cast(meta["price"].as_string(), Numeric(10, 2)), legacy_amount).label("amount"), cast(meta["quantity"].as_integer(), Integer).label("quantity"),
        provider_status.label("status"), literal("ALIPAY").label("channel"), OpcpayOperation.created_at.label("created_at"),
        paid_confirmed.label("confirmed_at"), checked.label("checked_at")).where(
            OpcpayOperation.kind == "PURCHASE", OpcpayOperation.deleted == 0, or_(~same_legacy, verified))
    return union_all(legacy, provider).subquery("admin_orders")


def _time(value, *, utc=False):
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc if utc else CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


class AdminOrderService:
    def __init__(self, db):
        self.db = db

    def list_orders(self, keyword, status, source, page_no, page_size):
        orders = order_projection()
        statement = select(orders, User.uid.label("user_uid"), User.email.label("email"), User.nickname.label("nickname"))\
            .outerjoin(User, User.id == orders.c.user_id)
        if status:
            if status not in STATUSES:
                raise AppException(code=1001, message="订单状态不正确")
            statement = statement.where(orders.c.status == status)
        if source:
            if source not in {"OPCPAY", "LEGACY"}:
                raise AppException(code=1001, message="订单来源不正确")
            statement = statement.where(orders.c.source == source)
        if keyword and keyword.strip():
            like = "%" + keyword.strip() + "%"
            statement = statement.where(or_(orders.c.order_no.like(like), orders.c.product_name.like(like),
                User.uid.like(like), User.email.like(like), User.mobile.like(like), User.nickname.like(like)))
        params = PageParams(page_no=page_no, page_size=page_size)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(orders.c.created_at.desc(), orders.c.order_no.desc(), orders.c.source.desc())
                               .offset(params.offset).limit(params.page_size)).mappings().all()
        records = [AdminOrderVO(source=r["source"], orderNo=r["order_no"], userUid=r["user_uid"], email=r["email"], nickname=r["nickname"],
            productName=r["product_name"], amount=r["amount"], quantity=r["quantity"], status=r["status"], channel=r["channel"],
            createdAt=_time(r["created_at"]), paymentConfirmedAt=_time(r["confirmed_at"], utc=r["source"] == "OPCPAY"),
            checkedAt=_time(r["checked_at"], utc=True)) for r in rows]
        return AdminOrderPageVO(records=records, total=total, pageNo=page_no, pageSize=page_size,
                                hasMore=params.offset + len(rows) < total)

    def confirmed_today(self, now=None):
        now = now or datetime.now(CHINA_TZ)
        start = now.astimezone(CHINA_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        utc_start = start.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        utc_end = end.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        orders = order_projection()
        # Provider observations are normalized UTC ISO strings; legacy payment timestamps are Beijing local time.
        statement = select(func.count(), func.coalesce(func.sum(orders.c.amount), 0)).where(orders.c.status == "PAID", or_(
            (orders.c.source == "OPCPAY") & (orders.c.confirmed_at >= utc_start) & (orders.c.confirmed_at < utc_end),
            (orders.c.source == "LEGACY") & (orders.c.confirmed_at >= start.replace(tzinfo=None).isoformat(sep=" "))
            & (orders.c.confirmed_at < end.replace(tzinfo=None).isoformat(sep=" "))))
        count, amount = self.db.execute(statement).one()
        return count, amount

    def successful_count(self, user_id):
        orders = order_projection()
        return self.db.scalar(select(func.count()).select_from(orders).where(orders.c.user_id == user_id, orders.c.status == "PAID")) or 0
