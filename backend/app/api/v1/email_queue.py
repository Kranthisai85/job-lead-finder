from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.dependencies import get_email_queue_service
from app.core.response import success_response
from app.email_queue.service import EmailQueueService
from app.email_queue.types import (
    EmailQueueItem,
    EmailQueueStatus,
    PendingEmailReviewList,
    SendResult,
)
from app.schemas.common import APIResponse

router = APIRouter(prefix="/email-queue", tags=["email-queue"])


class SendReadyBody(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=500)


class EmailDraftUpdateBody(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20000)


@router.get("/pending", response_model=APIResponse[PendingEmailReviewList])
async def list_pending_emails(
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[PendingEmailReviewList]:
    data = await service.list_pending()
    return success_response(
        message="Email queue review items retrieved successfully",
        data=data.model_dump(mode="json"),
    )


@router.post("/send-ready", response_model=APIResponse[SendResult])
async def send_ready_emails(
    body: SendReadyBody | None = None,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[SendResult]:
    limit = body.limit if body is not None else None
    result = await service.send_ready_to_send(limit=limit)
    return success_response(
        message="Ready-to-send emails processed",
        data=result.model_dump(mode="json"),
    )


@router.patch("/{item_id}", response_model=APIResponse[EmailQueueItem])
async def update_email_draft(
    item_id: str,
    body: EmailDraftUpdateBody,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[EmailQueueItem] | JSONResponse:
    """Edit subject/body on a PENDING queue item before Approve & Send."""
    if body.subject is None and body.body is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Provide subject and/or body to update",
                "data": None,
                "request_id": "",
            },
        )
    try:
        item = await service.update_draft(
            item_id,
            subject=body.subject,
            body=body.body,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": str(exc),
                "data": None,
                "request_id": "",
            },
        )
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
        message="Email draft updated successfully",
        data=item.model_dump(mode="json"),
    )


@router.post("/{item_id}/approve", response_model=APIResponse[EmailQueueItem])
async def approve_email(
    item_id: str,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[EmailQueueItem] | JSONResponse:
    """Approve and send in one step (PENDING → … → SENT/FAILED)."""
    item = await service.approve_and_send(item_id)
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
    if item.status == EmailQueueStatus.SENT:
        message = "Email approved and sent successfully"
    elif item.status == EmailQueueStatus.FAILED:
        message = "Email approved but send failed"
    else:
        message = "Email approved"
    return success_response(
        message=message,
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


@router.post("/{item_id}/ready-to-send", response_model=APIResponse[EmailQueueItem])
async def mark_ready_to_send(
    item_id: str,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[EmailQueueItem] | JSONResponse:
    item = await service.mark_ready_to_send(item_id)
    if item is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Approved queue item not found",
                "data": None,
                "request_id": "",
            },
        )
    return success_response(
        message="Email marked ready to send",
        data=item.model_dump(mode="json"),
    )


@router.post("/{item_id}/send", response_model=APIResponse[SendResult])
async def send_email(
    item_id: str,
    service: EmailQueueService = Depends(get_email_queue_service),
) -> APIResponse[SendResult] | JSONResponse:
    result = await service.send_one(item_id)
    if result.skipped and result.error and "not found" in (result.error or "").lower():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": result.error or "Queue item not found",
                "data": result.model_dump(mode="json"),
                "request_id": "",
            },
        )
    if result.skipped:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": result.error or "Item is not READY_TO_SEND",
                "data": result.model_dump(mode="json"),
                "request_id": "",
            },
        )
    message = "Email sent successfully" if result.success else "Email send failed"
    return success_response(
        message=message,
        data=result.model_dump(mode="json"),
    )
