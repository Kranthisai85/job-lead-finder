"""Deterministic approval / status transition service (no SMTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logger import get_logger
from app.email_queue.repository import QueueRepository
from app.email_queue.transitions import assert_transition_allowed
from app.email_queue.types import EmailQueueItem, EmailQueueStatus


class ApprovalService:
    """Validate and persist explicit outbound approval state changes."""

    def __init__(self, *, repository: QueueRepository | None = None) -> None:
        self.repository = repository or QueueRepository()
        self.logger = get_logger(__name__)

    async def approve(self, item_id: str) -> EmailQueueItem:
        return await self._transition(
            item_id,
            EmailQueueStatus.APPROVED,
            extra={"approved_at": datetime.now(timezone.utc), "error_message": None},
            log_action="approved",
        )

    async def skip(self, item_id: str, *, reason: str | None = None) -> EmailQueueItem:
        return await self._transition(
            item_id,
            EmailQueueStatus.SKIPPED,
            extra={"error_message": reason},
            log_action="skipped",
        )

    async def mark_ready_to_send(self, item_id: str) -> EmailQueueItem:
        return await self._transition(
            item_id,
            EmailQueueStatus.READY_TO_SEND,
            log_action="ready_to_send",
        )

    async def mark_sent(self, item_id: str) -> EmailQueueItem:
        return await self._transition(
            item_id,
            EmailQueueStatus.SENT,
            extra={"sent_at": datetime.now(timezone.utc), "error_message": None},
            log_action="sent",
        )

    async def mark_failed(self, item_id: str, *, error: str) -> EmailQueueItem:
        entry = await self.repository.find_by_id(item_id)
        if entry is None:
            raise LookupError(f"Queue item '{item_id}' not found")
        assert_transition_allowed(
            item_id=item_id,
            current=entry.status,
            target=EmailQueueStatus.FAILED,
        )
        retry_count = entry.retry_count + 1
        updated = await self.repository.apply_status(
            item_id,
            EmailQueueStatus.FAILED,
            extra={"error_message": error, "retry_count": retry_count},
            log_action="failed",
        )
        if updated is None:
            raise LookupError(f"Queue item '{item_id}' not found")
        self.logger.warning(
            "email_failed id=%s retry_count=%d error=%s",
            item_id,
            retry_count,
            error,
        )
        return self.repository.to_item(updated)

    async def _transition(
        self,
        item_id: str,
        target: EmailQueueStatus,
        *,
        extra: dict[str, Any] | None = None,
        log_action: str,
    ) -> EmailQueueItem:
        entry = await self.repository.find_by_id(item_id)
        if entry is None:
            raise LookupError(f"Queue item '{item_id}' not found")
        assert_transition_allowed(
            item_id=item_id,
            current=entry.status,
            target=target,
        )
        updated = await self.repository.apply_status(
            item_id,
            target,
            extra=extra,
            log_action=log_action,
        )
        if updated is None:
            raise LookupError(f"Queue item '{item_id}' not found")
        return self.repository.to_item(updated)
