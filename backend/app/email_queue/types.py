from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_serializer

from app.core.timezone import to_app_tz


def _serialize_ist(value: datetime | None) -> str | None:
    if value is None:
        return None
    return to_app_tz(value).isoformat()


class EmailQueueStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    READY_TO_SEND = "READY_TO_SEND"
    SKIPPED = "SKIPPED"
    SENDING = "SENDING"  # legacy; not used by Step 38 transitions
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"  # legacy reject path


class EmailQueueItem(BaseModel):
    id: str
    company_id: str
    contact_id: str
    recipient_name: str
    recipient_email: str
    subject: str
    body: str
    status: EmailQueueStatus
    created_at: datetime
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    error_message: str | None = None
    generation_source: str | None = None
    lead_score: float | None = None
    retry_count: int = 0

    @field_serializer("created_at", "approved_at", "sent_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return _serialize_ist(value)


class PendingEmailReviewItem(BaseModel):
    """Queue item enriched for dashboard approval review."""

    id: str
    company_id: str
    company_name: str | None = None
    company_website: str | None = None
    contact_name: str
    contact_email: str
    qualification_score: int | None = None
    qualification_status: str | None = None
    qualification_reasons: list[str] = Field(default_factory=list)
    subject: str
    body: str
    status: EmailQueueStatus
    lead_score: float | None = None
    generation_source: str | None = None
    created_at: datetime
    error_message: str | None = None
    sent_at: datetime | None = None
    approved_at: datetime | None = None

    @field_serializer("created_at", "approved_at", "sent_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return _serialize_ist(value)


class PendingEmailReviewList(BaseModel):
    items: list[PendingEmailReviewItem] = Field(default_factory=list)
    total: int = 0


class QueueStatistics(BaseModel):
    pending: int = 0
    approved: int = 0
    ready_to_send: int = 0
    skipped: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0


class SendResult(BaseModel):
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    attempted: int = 0
    errors: list[str] = Field(default_factory=list)
    queue_id: str | None = None
    recipient: str | None = None
    status: EmailQueueStatus | None = None
    success: bool | None = None
    error: str | None = None
