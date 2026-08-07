from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api import router as api_router
from app.api.v1.companies import router as companies_router
from app.api.v1.email_queue import router as email_queue_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import get_logger, setup_logging
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.middleware.logging import LoggingMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.scheduler.service import get_scheduler_service


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    await connect_to_mongo()
    scheduler_service = get_scheduler_service()
    try:
        scheduler_service.start()
    except Exception as exc:  # noqa: BLE001 — backend must still start
        get_logger(__name__).error("[SCHEDULER] startup_failed error=%s", exc)
    yield
    try:
        scheduler_service.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001
        get_logger(__name__).error("[SCHEDULER] shutdown_failed error=%s", exc)
    await close_mongo_connection()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=settings.api_description,
        lifespan=lifespan,
    )

    register_exception_handlers(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(LoggingMiddleware)
    application.add_middleware(RequestIdMiddleware)

    application.include_router(api_router)
    application.include_router(companies_router, prefix="/api/v1")
    application.include_router(email_queue_router, prefix="/api/v1")

    return application


app = create_app()
