from fastapi import APIRouter, Depends

from app.app_settings.service import AppSettingsService
from app.app_settings.types import AppSettings, AppSettingsUpdate
from app.core.dependencies import get_app_settings_service
from app.core.response import success_response
from app.schemas.common import APIResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=APIResponse[AppSettings])
async def get_app_settings(
    service: AppSettingsService = Depends(get_app_settings_service),
) -> APIResponse[AppSettings]:
    data = await service.get_settings()
    return success_response(
        message="App settings retrieved successfully",
        data=data.model_dump(),
    )


@router.put("", response_model=APIResponse[AppSettings])
async def update_app_settings(
    payload: AppSettingsUpdate,
    service: AppSettingsService = Depends(get_app_settings_service),
) -> APIResponse[AppSettings]:
    data = await service.update_settings(payload)
    return success_response(
        message="App settings updated successfully",
        data=data.model_dump(),
    )
