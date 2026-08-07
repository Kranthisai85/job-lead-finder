from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.dependencies import get_email_queue_service
from app.core.response import success_response
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueItem, PendingEmailReviewList
from app.schemas.common import APIResponse

router = APIRouter(prefix="/email-queue", tags=["email-queue"])


@router.get("/pending", response_model=APIResponse[PendingEmailReviewList])
async def list_pending_emails(
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[PendingEmailReviewList]:
    data = await service.list_pending()
    return success_response(
        message="Pending emails retrieved successfully",
        data=data.model_dump(mode="json"),
    )


@router.post("/{item_id}/approve", response_model=APIResponse[EmailQueueItem])
async def approve_email(
    item_id: str,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[EmailQueueItem] | JSONResponse:
    item = await service.approve(item_id)
    if item is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Pending queue item not found",
                "data": None,
                "request_id": "",
            },
        )
    return success_response(
        message="Email approved successfully",
        data=item.model_dump(mode="json"),
    )


@router.post("/{item_id}/skip", response_model=APIResponse[EmailQueueItem])
async def skip_email(
    item_id: str,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[EmailQueueItem] | JSONResponse:
    item = await service.skip(item_id)
    if item is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Pending queue item not found",
                "data": None,
                "request_id": "",
            },
        )
    return success_response(
        message="Email skipped successfully",
        data=item.model_dump(mode="json"),
    )
