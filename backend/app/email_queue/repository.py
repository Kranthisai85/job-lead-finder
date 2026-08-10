from __future__ import annotations

import re
from typing import Any

from app.core.logger import get_logger
from app.email_queue.document import EmailQueueEntry
from app.email_queue.types import EmailQueueItem, EmailQueueStatus
from app.repositories.base_repository import BaseRepository

# Queue statuses that mean "already handled / do not re-collect".
KNOWN_COMPANY_STATUSES: tuple[EmailQueueStatus, ...] = tuple(
    status for status in EmailQueueStatus if status != EmailQueueStatus.CANCELLED
)


class QueueRepository(BaseRepository[EmailQueueEntry]):
    MAX_RETRIES = 3

    def __init__(self) -> None:
        super().__init__(EmailQueueEntry)
        self.logger = get_logger(__name__)

    async def create(self, payload: dict[str, Any] | EmailQueueEntry) -> EmailQueueEntry:
        entry = await super().create(payload)
        self.logger.info(
            "email_queued id=%s company_id=%s contact_id=%s status=%s",
            entry.id,
            entry.company_id,
            entry.contact_id,
            entry.status.value,
        )
        return entry

    async def apply_status(
        self,
        item_id: str,
        status: EmailQueueStatus,
        *,
        extra: dict[str, Any] | None = None,
        log_action: str | None = None,
    ) -> EmailQueueEntry | None:
        update_data: dict[str, Any] = {"status": status}
        if extra:
            update_data.update(extra)
        updated = await self.update(item_id, update_data)
        if updated is not None and log_action:
            self.logger.info(
                "email_%s id=%s status=%s",
                log_action,
                item_id,
                status.value,
            )
        return updated

    async def get_pending(self) -> list[EmailQueueEntry]:
        return await self.find_many({"status": EmailQueueStatus.PENDING.value})

    async def get_approved(self) -> list[EmailQueueEntry]:
        return await self.find_many({"status": EmailQueueStatus.APPROVED.value})

    async def get_ready_to_send(self) -> list[EmailQueueEntry]:
        return await self.find_many({"status": EmailQueueStatus.READY_TO_SEND.value})

    async def get_review_queue(self) -> list[EmailQueueEntry]:
        """Items visible on the dashboard approval/send workflow."""
        return await self.find_many(
            {
                "status": {
                    "$in": [
                        EmailQueueStatus.PENDING.value,
                        EmailQueueStatus.APPROVED.value,
                        EmailQueueStatus.READY_TO_SEND.value,
                        EmailQueueStatus.FAILED.value,
                    ]
                }
            },
            sort=[("created_at", -1)],
        )

    async def get_retryable_failed(self) -> list[EmailQueueEntry]:
        return await self.find_many(
            {
                "status": EmailQueueStatus.FAILED.value,
                "retry_count": {"$lt": self.MAX_RETRIES},
            }
        )

    async def find_by_id_item(self, item_id: str) -> EmailQueueEntry | None:
        return await self.find_by_id(item_id)

    async def exists_known_for_company_keys(self, company_keys: list[str]) -> bool:
        keys = [key.strip() for key in company_keys if key and str(key).strip()]
        if not keys:
            return False
        entry = await self.model.find_one(
            {
                "company_id": {"$in": keys},
                "status": {"$in": [status.value for status in KNOWN_COMPANY_STATUSES]},
            }
        )
        return entry is not None

    async def exists_known_for_recipient_email(self, recipient_email: str) -> bool:
        email = (recipient_email or "").strip().lower()
        if not email:
            return False
        entry = await self.model.find_one(
            {
                "recipient_email": {"$regex": f"^{re.escape(email)}$", "$options": "i"},
                "status": {"$in": [status.value for status in KNOWN_COMPANY_STATUSES]},
            }
        )
        return entry is not None

    async def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for status in EmailQueueStatus:
            counts[status.value] = await self.count({"status": status.value})
        return counts

    @staticmethod
    def to_item(entry: EmailQueueEntry) -> EmailQueueItem:
        return EmailQueueItem(
            id=str(entry.id),
            company_id=entry.company_id,
            contact_id=entry.contact_id,
            recipient_name=entry.recipient_name,
            recipient_email=entry.recipient_email,
            subject=entry.subject,
            body=entry.body,
            status=entry.status,
            created_at=entry.created_at,
            approved_at=entry.approved_at,
            sent_at=entry.sent_at,
            error_message=entry.error_message,
            generation_source=entry.generation_source,
            lead_score=entry.lead_score,
            retry_count=entry.retry_count,
        )
