from __future__ import annotations

from app.ai.types import GeneratedEmail
from app.core.logger import get_logger
from app.email_queue.document import EmailQueueEntry
from app.email_queue.queue import compose_email_body
from app.email_queue.repository import QueueRepository
from app.email_queue.sender import EmailSender
from app.email_queue.types import (
    EmailQueueItem,
    EmailQueueStatus,
    QueueStatistics,
    SendResult,
)


class EmailQueueService:
    """Review queue and SMTP delivery for generated emails."""

    def __init__(
        self,
        *,
        repository: QueueRepository | None = None,
        sender: EmailSender | None = None,
    ) -> None:
        self.repository = repository or QueueRepository()
        self.sender = sender or EmailSender()
        self.logger = get_logger(__name__)

    async def enqueue(
        self,
        *,
        generated_email: GeneratedEmail,
        company_id: str,
        contact_id: str,
        recipient_name: str,
        recipient_email: str,
        lead_score: float | None = None,
    ) -> EmailQueueItem:
        body = compose_email_body(generated_email)
        entry = await self.repository.create(
            {
                "company_id": company_id,
                "contact_id": contact_id,
                "recipient_name": recipient_name,
                "recipient_email": recipient_email,
                "subject": generated_email.subject,
                "body": body,
                "status": EmailQueueStatus.PENDING,
                "generation_source": generated_email.generation_source,
                "lead_score": lead_score,
            }
        )
        self.logger.info(
            "email_queue_enqueue id=%s recipient=%s source=%s",
            entry.id,
            recipient_email,
            generated_email.generation_source,
        )
        return self.repository.to_item(entry)

    async def approve(self, item_id: str) -> EmailQueueItem | None:
        entry = await self.repository.approve(item_id)
        return self.repository.to_item(entry) if entry else None

    async def reject(self, item_id: str, *, reason: str | None = None) -> EmailQueueItem | None:
        entry = await self.repository.reject(item_id, reason=reason)
        return self.repository.to_item(entry) if entry else None

    async def send_pending(self) -> SendResult:
        approved = await self.repository.get_approved()
        retryable = await self.repository.get_retryable_failed()
        targets = approved + retryable
        result = SendResult()

        for entry in targets:
            item_result = await self._send_entry(entry)
            result.sent += item_result.sent
            result.failed += item_result.failed
            result.skipped += item_result.skipped
            result.errors.extend(item_result.errors)

        self.logger.info(
            "email_queue_send_pending sent=%d failed=%d skipped=%d",
            result.sent,
            result.failed,
            result.skipped,
        )
        return result

    async def send_one(self, item_id: str) -> SendResult:
        entry = await self.repository.find_by_id_item(item_id)
        if entry is None:
            return SendResult(skipped=1, errors=[f"Queue item '{item_id}' not found"])

        if entry.status not in {
            EmailQueueStatus.APPROVED,
            EmailQueueStatus.FAILED,
        }:
            return SendResult(
                skipped=1,
                errors=[f"Item '{item_id}' is not sendable (status={entry.status.value})"],
            )

        if (
            entry.status == EmailQueueStatus.FAILED
            and entry.retry_count >= self.repository.MAX_RETRIES
        ):
            return SendResult(
                skipped=1,
                errors=[f"Item '{item_id}' exceeded max retries"],
            )

        return await self._send_entry(entry)

    async def statistics(self) -> QueueStatistics:
        counts = await self.repository.count_by_status()
        total = sum(counts.values())
        return QueueStatistics(
            pending=counts.get(EmailQueueStatus.PENDING.value, 0),
            approved=counts.get(EmailQueueStatus.APPROVED.value, 0),
            sending=counts.get(EmailQueueStatus.SENDING.value, 0),
            sent=counts.get(EmailQueueStatus.SENT.value, 0),
            failed=counts.get(EmailQueueStatus.FAILED.value, 0),
            cancelled=counts.get(EmailQueueStatus.CANCELLED.value, 0),
            total=total,
        )

    async def _send_entry(self, entry: EmailQueueEntry) -> SendResult:
        item_id = str(entry.id)
        await self.repository.mark_sending(item_id)

        try:
            await self.sender.send(
                recipient_name=entry.recipient_name,
                recipient_email=entry.recipient_email,
                subject=entry.subject,
                body=entry.body,
            )
            await self.repository.mark_sent(item_id)
            if entry.retry_count > 0:
                self.logger.info(
                    "email_retry_success id=%s retry_count=%d", item_id, entry.retry_count
                )
            return SendResult(sent=1)
        except Exception as exc:
            await self.repository.mark_failed(item_id, error=str(exc))
            if entry.retry_count + 1 < self.repository.MAX_RETRIES:
                self.logger.warning(
                    "email_retry_scheduled id=%s retry_count=%d error=%s",
                    item_id,
                    entry.retry_count + 1,
                    exc,
                )
            return SendResult(failed=1, errors=[f"{item_id}: {exc}"])
