"""Email review queue and SMTP delivery."""

from app.email_queue.repository import QueueRepository
from app.email_queue.sender import EmailSender
from app.email_queue.service import EmailQueueService
from app.email_queue.types import (
    EmailQueueItem,
    EmailQueueStatus,
    QueueStatistics,
    SendResult,
)

__all__ = [
    "EmailQueueItem",
    "EmailQueueService",
    "EmailQueueStatus",
    "EmailSender",
    "QueueRepository",
    "QueueStatistics",
    "SendResult",
]
