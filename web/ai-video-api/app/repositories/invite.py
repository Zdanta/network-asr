from sqlalchemy import func, select

from app.models.invite import InviteRecord
from app.repositories.base import BaseRepository


class InviteRecordRepository(BaseRepository[InviteRecord]):
    model = InviteRecord

    def get_by_trigger_order_no(self, trigger_order_no: str) -> InviteRecord | None:
        return self.session.execute(
            select(InviteRecord).where(
                InviteRecord.trigger_order_no == trigger_order_no,
                InviteRecord.deleted == 0,
            )
        ).scalar_one_or_none()

    def list_by_inviter_id(self, inviter_id: int) -> list[InviteRecord]:
        return self.session.execute(
            select(InviteRecord)
            .where(InviteRecord.inviter_id == inviter_id, InviteRecord.deleted == 0)
            .order_by(InviteRecord.created_at.desc(), InviteRecord.id.desc())
        ).scalars().all()

    def sum_success_reward_amount(self, inviter_id: int):
        return self.session.execute(
            select(func.coalesce(func.sum(InviteRecord.reward_amount), 0)).where(
                InviteRecord.inviter_id == inviter_id,
                InviteRecord.reward_status == "SUCCESS",
                InviteRecord.deleted == 0,
            )
        ).scalar_one()
