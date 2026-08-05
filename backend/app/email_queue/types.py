from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EmailQueueStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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


class QueueStatistics(BaseModel):
    pending: int = 0
    approved: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0


class SendResult(BaseModel):
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
