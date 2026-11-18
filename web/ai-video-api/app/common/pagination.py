from math import ceil
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page_no - 1) * self.page_size


@dataclass
class PageResult(Generic[T]):
    records: list[T]
    total: int
    pageNo: int
    pageSize: int
    pages: int


def paginate(session: Session, statement: Select, params: PageParams) -> PageResult:
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = session.execute(count_statement).scalar_one()
    records = session.execute(statement.offset(params.offset).limit(params.page_size)).scalars().all()

    return PageResult(
        records=records,
        total=total,
        pageNo=params.page_no,
        pageSize=params.page_size,
        pages=ceil(total / params.page_size) if total else 0,
    )
