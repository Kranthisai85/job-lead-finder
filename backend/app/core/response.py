from typing import Any

from app.core.logger import get_request_id
from app.schemas.common import APIResponse


def success_response(
    *,
    message: str = "",
    data: dict[str, Any] | list[Any] | None = None,
) -> APIResponse[Any]:
    return APIResponse(
        success=True,
        message=message,
        data=data if data is not None else {},
        request_id=get_request_id(),
    )


def error_response(
    *,
    message: str,
    data: dict[str, Any] | None = None,
) -> APIResponse[Any]:
    return APIResponse(
        success=False,
        message=message,
        data=data or {},
        request_id=get_request_id(),
    )
