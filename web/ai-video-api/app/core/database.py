from collections.abc import Generator
from functools import lru_cache
from time import perf_counter

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine_options = {
        "echo": settings.database_echo,
        "pool_pre_ping": settings.database_pool_pre_ping,
        "future": True,
    }

    if not make_url(settings.database_url).drivername.startswith("sqlite"):
        engine_options.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_recycle": settings.database_pool_recycle_seconds,
            }
        )

    return create_engine(settings.database_url, **engine_options)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_engine(),
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_database() -> dict:
    started_at = perf_counter()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "UP",
        "latencyMs": round((perf_counter() - started_at) * 1000, 2),
    }
