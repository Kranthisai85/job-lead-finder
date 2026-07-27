from fastapi import APIRouter, Request, status
from starlette.responses import Response

from app.db.mongo import ping_mongodb
from app.schemas.common import HealthData

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthData)
async def health_check(request: Request, response: Response) -> HealthData:
    mongodb_connected = await ping_mongodb()
    request_id = getattr(request.state, "request_id", "")

    if not mongodb_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthData(
        status="healthy" if mongodb_connected else "unhealthy",
        mongodb="connected" if mongodb_connected else "disconnected",
        request_id=request_id,
    )
