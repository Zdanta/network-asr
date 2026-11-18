from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestLogMiddleware
from app.workers.media_import_queue import media_import_worker_queue
from app.workers.media_cleanup import media_cleanup_worker
from app.workers.task_queue import task_worker_queue
from app.modules.payment.opcpay_worker import opcpay_recovery
from app.modules.invite.settlement import settlement_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    task_worker_queue.start()
    media_import_worker_queue.start()
    media_cleanup_worker.start()
    if get_settings().opcpay_enabled:
        opcpay_recovery.start()
        settlement_worker.start()
    try:
        yield
    finally:
        opcpay_recovery.stop()
        settlement_worker.stop()
        media_cleanup_worker.stop()
        media_import_worker_queue.stop()
        task_worker_queue.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    )

    register_exception_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
