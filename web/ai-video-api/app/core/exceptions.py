import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.response import ApiResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _error_response(code: int, message: str, status_code: int) -> JSONResponse:
    payload = ApiResponse[None](code=code, message=message, data=None)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        return _error_response(exc.code, exc.message, exc.status_code)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        return _error_response(exc.status_code, message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("request validation failed: %s", [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()])
        return _error_response(1001, "请求参数不正确，请检查后重试", 422)

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_exception(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database operation failed")
        return _error_response(5001, "数据库操作失败，请稍后重试", 500)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected server error")
        return _error_response(5000, "服务暂时不可用，请稍后重试", 500)
