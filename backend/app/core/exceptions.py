from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logger import get_logger, get_request_id
from app.exceptions import (
    DatabaseConnectionError,
    DuplicateRecordError,
    NotFoundError,
    RepositoryError,
)
from app.schemas.common import APIResponse


class AppException(Exception):
    def __init__(
        self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _build_error_response(
    *,
    message: str,
    status_code: int,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = APIResponse(
        success=False,
        message=message,
        data=data or {},
        request_id=get_request_id(),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    _ = request
    return _build_error_response(
        message="Validation error",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        data={"errors": exc.errors()},
    )


async def repository_exception_handler(
    request: Request,
    exc: RepositoryError,
) -> JSONResponse:
    _ = request
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if isinstance(exc, NotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DuplicateRecordError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, DatabaseConnectionError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return _build_error_response(message=str(exc), status_code=status_code)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    _ = request
    return _build_error_response(message=exc.message, status_code=exc.status_code)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = request
    logger = get_logger(__name__)
    logger.exception("Unhandled exception: %s", exc)
    return _build_error_response(
        message="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RepositoryError,
        repository_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        AppException,
        app_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
