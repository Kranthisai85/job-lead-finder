import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logger import set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_request_id = request.headers.get(settings.request_id_header)
        request_id = incoming_request_id or str(uuid.uuid4())

        request.state.request_id = request_id
        set_request_id(request_id)

        response = await call_next(request)
        response.headers[settings.request_id_header] = request_id
        return response
