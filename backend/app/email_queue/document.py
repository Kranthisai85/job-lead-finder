from __future__ import annotations

from datetime import datetime

from pymongo import IndexModel

from app.email_queue.types import EmailQueueStatus
from app.models.base import BaseDocument


class EmailQueueEntry(BaseDocument):
    company_id: str
    contact_id: str
    recipient_name: str
    recipient_email: str
    subject: str
    body: str
    status: EmailQueueStatus = EmailQueueStatus.PENDING
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    error_message: str | None = None
    generation_source: str | None = None
    lead_score: float | None = None
    retry_count: int = 0

    class Settings:
        name = "email_queue"
        indexes = [
            IndexModel([("status", 1), ("created_at", -1)]),
            IndexModel([("company_id", 1), ("contact_id", 1)]),
            IndexModel([("recipient_email", 1)]),
        ]
