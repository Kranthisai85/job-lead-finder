"""Email review queue and SMTP delivery."""

from app.email_queue.approval import ApprovalService
from app.email_queue.repository import QueueRepository
from app.email_queue.sender import EmailSender
from app.email_queue.service import EmailQueueService
from app.email_queue.transitions import ALLOWED_TRANSITIONS, InvalidTransitionError, can_transition
from app.email_queue.types import (
    EmailQueueItem,
    EmailQueueStatus,
    PendingEmailReviewItem,
    PendingEmailReviewList,
    QueueStatistics,
    SendResult,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ApprovalService",
    "EmailQueueItem",
    "EmailQueueService",
    "EmailQueueStatus",
    "EmailSender",
    "InvalidTransitionError",
    "PendingEmailReviewItem",
    "PendingEmailReviewList",
    "QueueRepository",
    "QueueStatistics",
    "SendResult",
    "can_transition",
]
