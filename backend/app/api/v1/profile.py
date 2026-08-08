from fastapi import APIRouter, Depends

from app.core.dependencies import get_sender_profile_service
from app.core.response import success_response
from app.schemas.common import APIResponse
from app.sender_profile.service import SenderProfileService
from app.sender_profile.types import SenderProfile, SenderProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=APIResponse[SenderProfile])
async def get_sender_profile(
    service: SenderProfileService = Depends(get_sender_profile_service),
) -> APIResponse[SenderProfile]:
    data = await service.get_profile()
    return success_response(
        message="Sender profile retrieved successfully",
        data=data.model_dump(),
    )


@router.put("", response_model=APIResponse[SenderProfile])
async def update_sender_profile(
    payload: SenderProfileUpdate,
    service: SenderProfileService = Depends(get_sender_profile_service),
) -> APIResponse[SenderProfile]:
    data = await service.update_profile(payload)
    return success_response(
        message="Sender profile updated successfully",
        data=data.model_dump(),
    )
