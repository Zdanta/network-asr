from sqlalchemy import func, select

from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    model = Task

    def get_by_task_no(self, task_no: str, user_id: int | None = None) -> Task | None:
        statement = select(Task).where(Task.task_no == task_no, Task.deleted == 0)
        if user_id is not None:
            statement = statement.where(Task.user_id == user_id)
        return self.session.execute(statement).scalar_one_or_none()

    def count_by_user_id(self, user_id: int) -> int:
        return self.session.execute(
            select(func.count()).select_from(Task).where(Task.user_id == user_id, Task.deleted == 0)
        ).scalar_one()
