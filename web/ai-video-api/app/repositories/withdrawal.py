from sqlalchemy import func, select

from app.models.withdrawal import WithdrawalOrder
from app.repositories.base import BaseRepository


class WithdrawalOrderRepository(BaseRepository[WithdrawalOrder]):
    model = WithdrawalOrder

    def get_by_withdraw_no(self, withdraw_no: str, user_id: int | None = None) -> WithdrawalOrder | None:
        statement = select(WithdrawalOrder).where(
            WithdrawalOrder.withdraw_no == withdraw_no,
            WithdrawalOrder.deleted == 0,
        )
        if user_id is not None:
            statement = statement.where(WithdrawalOrder.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()

    def list_by_user_id(self, user_id: int) -> list[WithdrawalOrder]:
        return self.session.execute(
            select(WithdrawalOrder)
            .where(WithdrawalOrder.user_id == user_id, WithdrawalOrder.deleted == 0)
            .order_by(WithdrawalOrder.created_at.desc(), WithdrawalOrder.id.desc())
        ).scalars().all()

    def sum_amount_by_status(self, user_id: int, status: str):
        return self.session.execute(
            select(func.coalesce(func.sum(WithdrawalOrder.amount), 0)).where(
                WithdrawalOrder.user_id == user_id,
                WithdrawalOrder.status == status,
                WithdrawalOrder.deleted == 0,
            )
        ).scalar_one()
