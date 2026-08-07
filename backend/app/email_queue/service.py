from __future__ import annotations

from app.ai.types import GeneratedEmail
from app.core.logger import get_logger
from app.email_queue.approval import ApprovalService
from app.email_queue.document import EmailQueueEntry
from app.email_queue.queue import compose_email_body
from app.email_queue.repository import QueueRepository
from app.email_queue.sender import EmailSender
from app.email_queue.transitions import InvalidTransitionError
from app.email_queue.types import (
    EmailQueueItem,
    EmailQueueStatus,
    PendingEmailReviewItem,
    PendingEmailReviewList,
    QueueStatistics,
    SendResult,
)
from app.repositories.company_repository import CompanyRepository


class EmailQueueService:
    """Review queue and gated delivery for generated emails."""

    def __init__(
        self,
        *,
        repository: QueueRepository | None = None,
        sender: EmailSender | None = None,
        company_repository: CompanyRepository | None = None,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self.repository = repository or QueueRepository()
        self.sender = sender or EmailSender()
        self.company_repository = company_repository or CompanyRepository()
        self.approval = approval_service or ApprovalService(repository=self.repository)
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

    async def list_pending(self) -> PendingEmailReviewList:
        entries = await self.repository.get_pending()
        items: list[PendingEmailReviewItem] = []
        for entry in entries:
            company = await self.company_repository.find_by_id(entry.company_id)
            score = None
            status = None
            reasons: list[str] = []
            name = None
            website = None
            if company is not None:
                name = company.name
                website = company.website
                score = company.qualification_score
                status = company.qualification_status
                reasons = list(company.qualification_reasons or [])
            items.append(
                PendingEmailReviewItem(
                    id=str(entry.id),
                    company_id=entry.company_id,
                    company_name=name,
                    company_website=website,
                    contact_name=entry.recipient_name,
                    contact_email=entry.recipient_email,
                    qualification_score=score,
                    qualification_status=status,
                    qualification_reasons=reasons,
                    subject=entry.subject,
                    body=entry.body,
                    status=entry.status,
                    lead_score=entry.lead_score,
                    generation_source=entry.generation_source,
                    created_at=entry.created_at,
                )
            )
        return PendingEmailReviewList(items=items, total=len(items))

    async def approve(self, item_id: str) -> EmailQueueItem | None:
        try:
            return await self.approval.approve(item_id)
        except (LookupError, InvalidTransitionError):
            return None

    async def skip(self, item_id: str, *, reason: str | None = None) -> EmailQueueItem | None:
        try:
            return await self.approval.skip(item_id, reason=reason)
        except (LookupError, InvalidTransitionError):
            return None

    async def mark_ready_to_send(self, item_id: str) -> EmailQueueItem | None:
        try:
            return await self.approval.mark_ready_to_send(item_id)
        except (LookupError, InvalidTransitionError):
            return None

    async def reject(self, item_id: str, *, reason: str | None = None) -> EmailQueueItem | None:
        # Legacy CANCELLED path — not part of Step 38 approval gate.
        updated = await self.repository.apply_status(
            item_id,
            EmailQueueStatus.CANCELLED,
            extra={"error_message": reason},
            log_action="rejected",
        )
        return self.repository.to_item(updated) if updated else None

    async def send_pending(self) -> SendResult:
        """Send only READY_TO_SEND items. Never PENDING or APPROVED."""
        targets = await self.repository.get_ready_to_send()
        result = SendResult()

        for entry in targets:
            item_result = await self._send_entry(entry)
            result.sent += item_result.sent
            result.failed += item_result.failed
            result.skipped += item_result.skipped
            result.errors.extend(item_result.errors)

        self.logger.info(
            "email_queue_send_ready sent=%d failed=%d skipped=%d",
            result.sent,
            result.failed,
            result.skipped,
        )
        return result

    async def send_one(self, item_id: str) -> SendResult:
        entry = await self.repository.find_by_id_item(item_id)
        if entry is None:
            return SendResult(skipped=1, errors=[f"Queue item '{item_id}' not found"])

        if entry.status != EmailQueueStatus.READY_TO_SEND:
            return SendResult(
                skipped=1,
                errors=[f"Item '{item_id}' is not sendable (status={entry.status.value})"],
            )

        return await self._send_entry(entry)

    async def statistics(self) -> QueueStatistics:
        counts = await self.repository.count_by_status()
        total = sum(counts.values())
        return QueueStatistics(
            pending=counts.get(EmailQueueStatus.PENDING.value, 0),
            approved=counts.get(EmailQueueStatus.APPROVED.value, 0),
            ready_to_send=counts.get(EmailQueueStatus.READY_TO_SEND.value, 0),
            skipped=counts.get(EmailQueueStatus.SKIPPED.value, 0),
            sending=counts.get(EmailQueueStatus.SENDING.value, 0),
            sent=counts.get(EmailQueueStatus.SENT.value, 0),
            failed=counts.get(EmailQueueStatus.FAILED.value, 0),
            cancelled=counts.get(EmailQueueStatus.CANCELLED.value, 0),
            total=total,
        )

    async def _send_entry(self, entry: EmailQueueEntry) -> SendResult:
        item_id = str(entry.id)
        if entry.status != EmailQueueStatus.READY_TO_SEND:
            return SendResult(
                skipped=1,
                errors=[f"Item '{item_id}' is not READY_TO_SEND"],
            )

        try:
            await self.sender.send(
                recipient_name=entry.recipient_name,
                recipient_email=entry.recipient_email,
                subject=entry.subject,
                body=entry.body,
            )
            await self.approval.mark_sent(item_id)
            if entry.retry_count > 0:
                self.logger.info(
                    "email_retry_success id=%s retry_count=%d", item_id, entry.retry_count
                )
            return SendResult(sent=1)
        except Exception as exc:
            await self.approval.mark_failed(item_id, error=str(exc))
            return SendResult(failed=1, errors=[f"{item_id}: {exc}"])
