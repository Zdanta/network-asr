from datetime import datetime

from sqlalchemy import func, select

from app.models.payment import PayNotifyLog, PayOrder
from app.repositories.base import BaseRepository


class PayOrderRepository(BaseRepository[PayOrder]):
    model = PayOrder

    def get_by_order_no(self, order_no: str, user_id: int | None = None) -> PayOrder | None:
        statement = select(PayOrder).where(PayOrder.order_no == order_no, PayOrder.deleted == 0)
        if user_id is not None:
            statement = statement.where(PayOrder.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()

    def count_success_orders(self, user_id: int) -> int:
        return self.session.execute(
            select(func.count()).select_from(PayOrder).where(
                PayOrder.user_id == user_id,
                PayOrder.status == "SUCCESS",
                PayOrder.deleted == 0,
            )
        ).scalar_one()

    def get_recent_init_order(self, user_id: int, product_type: str, since: datetime) -> PayOrder | None:
        return self.session.execute(
            select(PayOrder)
            .where(
                PayOrder.user_id == user_id,
                PayOrder.product_type == product_type,
                PayOrder.status == "INIT",
                PayOrder.deleted == 0,
                PayOrder.created_at >= since,
            )
            .order_by(PayOrder.created_at.desc(), PayOrder.id.desc())
            .limit(1)
        ).scalar_one_or_none()


class PayNotifyLogRepository(BaseRepository[PayNotifyLog]):
    model = PayNotifyLog
