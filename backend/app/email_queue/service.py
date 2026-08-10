from __future__ import annotations

import re

from app.ai.types import GeneratedEmail
from app.app_settings.service import AppSettingsService
from app.contact_discovery.validators import is_outbound_safe_email
from app.core.daily_logging import ensure_daily_run_handler
from app.core.logger import get_logger
from app.email.exceptions import SmtpError
from app.email.smtp_client import sanitize_smtp_error_message
from app.email_queue.approval import ApprovalService
from app.email_queue.deliverability import domain_accepts_mail, email_domain
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
from app.sender_profile.service import SenderProfileService
from app.sender_profile.types import finalize_body_for_send
from app.utils.url import canonical_lead_website

_RECIPIENT_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailQueueService:
    """Review queue and gated delivery for generated emails."""

    def __init__(
        self,
        *,
        repository: QueueRepository | None = None,
        sender: EmailSender | None = None,
        company_repository: CompanyRepository | None = None,
        approval_service: ApprovalService | None = None,
        app_settings_service: AppSettingsService | None = None,
    ) -> None:
        self.repository = repository or QueueRepository()
        self.sender = sender or EmailSender()
        self.company_repository = company_repository or CompanyRepository()
        self.approval = approval_service or ApprovalService(repository=self.repository)
        self.sender_profile = SenderProfileService()
        self.app_settings = app_settings_service or AppSettingsService()
        self.logger = get_logger(__name__)

    async def is_duplicate_company(self, *, website: str) -> bool:
        """True when settings say skip duplicates and this website is already queued."""
        settings = await self.app_settings.get_settings()
        if not settings.skip_duplicate_companies:
            return False
        keys = await self._company_lookup_keys(website)
        known = await self.repository.exists_known_for_company_keys(keys)
        if known:
            self.logger.info(
                "[QUEUE] duplicate_company website=%s keys=%s",
                website,
                keys,
            )
        return known

    async def is_duplicate_recipient(self, *, recipient_email: str) -> bool:
        """True when settings say skip duplicates and this email was already queued."""
        settings = await self.app_settings.get_settings()
        if not settings.skip_duplicate_companies:
            return False
        known = await self.repository.exists_known_for_recipient_email(recipient_email)
        if known:
            self.logger.info(
                "[QUEUE] duplicate_recipient email=%s",
                recipient_email,
            )
        return known

    async def _company_lookup_keys(self, website: str) -> list[str]:
        canonical = canonical_lead_website(website or "")
        keys: list[str] = []
        if canonical:
            keys.append(canonical)
            host_key = canonical.replace("https://", "").replace("http://", "").strip("/")
            if host_key:
                keys.append(host_key)
            company = await self.company_repository.find_one({"website": canonical})
            if company is not None and company.id is not None:
                keys.append(str(company.id))
            # Also match older rows that stored the raw seed website.
            raw = (website or "").strip()
            if raw and raw not in keys:
                keys.append(raw)
                raw_host = raw.replace("https://", "").replace("http://", "").strip("/")
                if raw_host and raw_host not in keys:
                    keys.append(raw_host)
        # Preserve order, drop empties/dupes.
        seen: set[str] = set()
        unique: list[str] = []
        for key in keys:
            value = key.strip()
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique

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
        profile = await self.sender_profile.get_profile()
        body = compose_email_body(generated_email, profile=profile)
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
        """Dashboard review list: PENDING, APPROVED, READY_TO_SEND, FAILED."""
        entries = await self.repository.get_review_queue()
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
                    error_message=entry.error_message,
                    sent_at=entry.sent_at,
                    approved_at=entry.approved_at,
                )
            )
        return PendingEmailReviewList(items=items, total=len(items))

    async def approve(self, item_id: str) -> EmailQueueItem | None:
        """Approve only (PENDING → APPROVED). Prefer approve_and_send for dashboard."""
        try:
            return await self.approval.approve(item_id)
        except (LookupError, InvalidTransitionError):
            return None

    async def approve_and_send(self, item_id: str) -> EmailQueueItem | None:
        """One-click dashboard action: PENDING → APPROVED → READY_TO_SEND → send.

        Reuses existing transition + send services. Does not bypass SMTP gates
        (DRY_RUN / SMTP_ENABLED still apply inside EmailSender).
        """
        approved = await self.approve(item_id)
        if approved is None:
            return None

        ready = await self.mark_ready_to_send(item_id)
        if ready is None:
            entry = await self.repository.find_by_id_item(item_id)
            return self.repository.to_item(entry) if entry else approved

        send_result = await self.send_one(item_id)
        self.logger.info(
            "[EMAIL] approve_and_send queue_id=%s send_success=%s status=%s error=%s",
            item_id,
            send_result.success,
            send_result.status.value if send_result.status else None,
            send_result.error,
        )
        entry = await self.repository.find_by_id_item(item_id)
        return self.repository.to_item(entry) if entry else ready

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
        """Backward-compatible alias — sends ONLY READY_TO_SEND items."""
        return await self.send_ready_to_send()

    async def send_ready_to_send(self, limit: int | None = None) -> SendResult:
        """Send READY_TO_SEND records independently. Never PENDING/APPROVED."""
        ensure_daily_run_handler()
        targets = await self.repository.get_ready_to_send()
        if limit is not None:
            targets = targets[: max(0, int(limit))]

        result = SendResult(attempted=len(targets))
        for entry in targets:
            item_result = await self._send_entry(entry)
            result.sent += item_result.sent
            result.failed += item_result.failed
            result.skipped += item_result.skipped
            result.errors.extend(item_result.errors)

        self.logger.info(
            "[EMAIL] batch_complete attempted=%d sent=%d failed=%d skipped=%d",
            result.attempted,
            result.sent,
            result.failed,
            result.skipped,
        )
        return result

    async def send_one(self, item_id: str) -> SendResult:
        ensure_daily_run_handler()
        entry = await self.repository.find_by_id_item(item_id)
        if entry is None:
            return SendResult(
                skipped=1,
                attempted=0,
                success=False,
                queue_id=item_id,
                error=f"Queue item '{item_id}' not found",
                errors=[f"Queue item '{item_id}' not found"],
            )

        if entry.status != EmailQueueStatus.READY_TO_SEND:
            message = f"Item '{item_id}' is not sendable (status={entry.status.value})"
            return SendResult(
                skipped=1,
                attempted=0,
                success=False,
                queue_id=item_id,
                recipient=entry.recipient_email,
                status=entry.status,
                error=message,
                errors=[message],
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

    def _validate_sendable_entry(self, entry: EmailQueueEntry) -> str | None:
        if not entry.company_id or not entry.contact_id:
            return "Missing company/contact association"
        email = (entry.recipient_email or "").strip()
        if not email:
            return "Missing recipient email"
        if not _RECIPIENT_EMAIL_RE.match(email):
            return "Invalid recipient email"
        if not is_outbound_safe_email(email):
            return "Recipient is a generic inbox (hello@/info@/support@) — skip to avoid bounces"
        if not (entry.subject or "").strip():
            return "Missing email subject"
        if not (entry.body or "").strip():
            return "Missing email body"
        return None

    async def _send_entry(self, entry: EmailQueueEntry) -> SendResult:
        item_id = str(entry.id)
        recipient = entry.recipient_email
        if entry.status != EmailQueueStatus.READY_TO_SEND:
            message = f"Item '{item_id}' is not READY_TO_SEND"
            return SendResult(
                skipped=1,
                attempted=1,
                success=False,
                queue_id=item_id,
                recipient=recipient,
                status=entry.status,
                error=message,
                errors=[message],
            )

        validation_error = self._validate_sendable_entry(entry)
        if validation_error is not None:
            self.logger.error(
                "[EMAIL] send_failed queue_id=%s reason=%s",
                item_id,
                validation_error,
            )
            await self.approval.mark_failed(item_id, error=validation_error)
            return SendResult(
                failed=1,
                attempted=1,
                success=False,
                queue_id=item_id,
                recipient=recipient,
                status=EmailQueueStatus.FAILED,
                error=validation_error,
                errors=[f"{item_id}: {validation_error}"],
            )

        domain = email_domain(recipient or "")
        if domain and not await domain_accepts_mail(domain):
            message = f"No MX records for domain '{domain}'"
            self.logger.error(
                "[EMAIL] send_failed queue_id=%s reason=%s",
                item_id,
                message,
            )
            await self.approval.mark_failed(item_id, error=message)
            return SendResult(
                failed=1,
                attempted=1,
                success=False,
                queue_id=item_id,
                recipient=recipient,
                status=EmailQueueStatus.FAILED,
                error=message,
                errors=[f"{item_id}: {message}"],
            )

        self.logger.info(
            "[EMAIL] send_started queue_id=%s recipient=%s",
            item_id,
            recipient,
        )
        try:
            profile = await self.sender_profile.get_profile()
            body = finalize_body_for_send(entry.body, profile)
            if body != entry.body:
                entry.body = body
                await entry.save()
            await self.sender.send(
                recipient_name=entry.recipient_name,
                recipient_email=entry.recipient_email,
                subject=entry.subject,
                body=body,
            )
            await self.approval.mark_sent(item_id)
            self.logger.info(
                "[EMAIL] sent queue_id=%s recipient=%s",
                item_id,
                recipient,
            )
            if entry.retry_count > 0:
                self.logger.info(
                    "email_retry_success id=%s retry_count=%d", item_id, entry.retry_count
                )
            return SendResult(
                sent=1,
                attempted=1,
                success=True,
                queue_id=item_id,
                recipient=recipient,
                status=EmailQueueStatus.SENT,
            )
        except Exception as exc:
            safe_error = (
                exc.safe_message if isinstance(exc, SmtpError) else sanitize_smtp_error_message(exc)
            )
            self.logger.error(
                "[EMAIL] send_failed queue_id=%s reason=%s",
                item_id,
                safe_error,
            )
            await self.approval.mark_failed(item_id, error=safe_error)
            return SendResult(
                failed=1,
                attempted=1,
                success=False,
                queue_id=item_id,
                recipient=recipient,
                status=EmailQueueStatus.FAILED,
                error=safe_error,
                errors=[f"{item_id}: {safe_error}"],
            )
