from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, PageResult, paginate
from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id_: int) -> ModelT | None:
        return self.session.get(self.model, id_)

    def get_required(self, id_: int) -> ModelT:
        instance = self.get(id_)
        if instance is None:
            raise ValueError(f"{self.model.__name__} not found: {id_}")
        return instance

    def list(self, statement: Select | None = None) -> Sequence[ModelT]:
        query = statement if statement is not None else select(self.model)
        return self.session.execute(query).scalars().all()

    def page(self, params: PageParams, statement: Select | None = None) -> PageResult[ModelT]:
        query = statement if statement is not None else select(self.model)
        return paginate(self.session, query, params)

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        self.session.flush()
        return instance

    def add_all(self, instances: Sequence[ModelT]) -> Sequence[ModelT]:
        self.session.add_all(instances)
        self.session.flush()
        return instances

    def delete(self, instance: ModelT) -> None:
        self.session.delete(instance)
        self.session.flush()

    def soft_delete(self, instance: ModelT) -> ModelT:
        if not hasattr(instance, "deleted"):
            raise TypeError(f"{self.model.__name__} does not support logical delete")
        setattr(instance, "deleted", 1)
        self.session.flush()
        return instance
