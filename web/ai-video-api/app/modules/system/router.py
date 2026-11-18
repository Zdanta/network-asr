from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import check_database
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response

router = APIRouter()


class DatabaseHealth(BaseModel):
    status: str
    latencyMs: float | None = None


class HealthData(BaseModel):
    status: str
    appName: str
    appVersion: str
    environment: str
    database: DatabaseHealth | None = None


@router.get("/health", response_model=ApiResponse[HealthData])
def health() -> ApiResponse[HealthData]:
    settings = get_settings()
    database = None

    if settings.health_check_database:
        try:
            database = DatabaseHealth(**check_database())
        except SQLAlchemyError as exc:
            raise AppException(code=5001, message="数据库健康检查失败", status_code=503) from exc

    return success_response(
        HealthData(
            status="UP",
            appName=settings.app_name,
            appVersion=settings.app_version,
            environment=settings.app_env,
            database=database,
        )
    )
