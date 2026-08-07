"""Step 41 — end-to-end production verification (mocked external boundaries only)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.types import GeneratedEmail
from app.core.config import Settings, settings
from app.core.daily_logging import (
    daily_log_filename,
    detach_daily_run_handler,
    ensure_daily_run_handler,
    list_daily_log_files,
    prune_daily_logs,
)
from app.core.logger import get_logger
from app.email.sender import EmailSender
from app.email_queue.approval import ApprovalService
from app.email_queue.repository import QueueRepository
from app.email_queue.service import EmailQueueService
from app.email_queue.transitions import InvalidTransitionError, can_transition
from app.email_queue.types import EmailQueueStatus
from app.lead_generation.service import LeadGenerationService
from app.lead_scoring.service import LeadScoringService
from app.personalization.service import CompanyPersonalizationService
from app.pipeline.persistence import PipelinePersistenceService
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.scheduler.jobs import DailyLeadGenerationJob
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.service import SchedulerService
from tests.test_lead_generation import build_orchestrator, make_collection_report
from tests.test_personalization import make_lead


class RecordingTransport:
    """Fake SMTP transport — never opens a network connection."""

    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.fail_with: Exception | None = None
        self.call_count = 0

    def send_message(self, message: Any) -> None:
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _block_real_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the suite if smtplib is accidentally used."""

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Real SMTP connection attempted during Step 41 E2E tests")

    monkeypatch.setattr("smtplib.SMTP", _boom)
    monkeypatch.setattr("smtplib.SMTP_SSL", _boom)
    monkeypatch.setattr(settings, "smtp_enabled", False)
    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(settings, "smtp_password", "super-secret-e2e-password")


def _generated(
    *,
    subject: str = "Flutter idea for Acme",
    body: str = "I noticed Acme builds issue tracking tools.",
    opening: str = "Hi Ada,",
    cta: str = "Open to a quick call?",
) -> GeneratedEmail:
    return GeneratedEmail(
        subject=subject,
        opening=opening,
        body=body,
        cta=cta,
        generation_source="fallback",
    )


async def _enqueue_ready(
    service: EmailQueueService,
    *,
    company_id: str,
    contact_id: str,
    recipient_name: str,
    recipient_email: str,
    generated: GeneratedEmail | None = None,
) -> str:
    item = await service.enqueue(
        generated_email=generated or _generated(),
        company_id=company_id,
        contact_id=contact_id,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        lead_score=88.0,
    )
    await service.approve(item.id)
    await service.mark_ready_to_send(item.id)
    return item.id


# ---------------------------------------------------------------------------
# Config / dashboard safety
# ---------------------------------------------------------------------------


def test_e2e_smtp_defaults_remain_safe() -> None:
    assert Settings.model_fields["smtp_enabled"].default is False
    assert Settings.model_fields["dry_run"].default is True
    assert settings.smtp_enabled is False
    assert settings.dry_run is True


def test_e2e_dashboard_exposes_required_actions() -> None:
    page = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "EmailQueuePage.jsx"
    service = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "services"
        / "emailQueueService.js"
    )
    page_text = page.read_text(encoding="utf-8")
    service_text = service.read_text(encoding="utf-8")

    for token in (
        "PENDING",
        "APPROVED",
        "READY_TO_SEND",
        "SENT",
        "FAILED",
        "SKIPPED",
        "Approve",
        "Ready to Send",
        "Send",
        "qualification_score",
        "qualification_status",
        "qualification_reasons",
        "error_message",
    ):
        assert token in page_text

    for fn in ("approveEmail", "skipEmail", "markReadyToSend", "sendEmail"):
        assert fn in service_text


# ---------------------------------------------------------------------------
# Complete lead flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_complete_lead_flow_to_sent(
    test_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = RecordingTransport()
    queue = EmailQueueService(
        sender=EmailSender(transport=transport, dry_run=False, smtp_enabled=True)
    )

    lead = make_lead(
        company_name="Acme",
        description="Issue tracking for software teams",
        has_mobile_app=False,
        technologies=["React", "Tailwind"],
    )
    score = LeadScoringService().score(lead)
    lead.outbound_lead_score = score
    assert score.score >= 0
    assert score.status is not None

    persist = await PipelinePersistenceService().persist(lead)
    assert persist.company_id
    company = await CompanyRepository().find_by_id(persist.company_id)
    assert company is not None
    assert company.qualification_score == score.score
    assert company.qualification_status == score.status.value
    assert company.qualification_reasons == list(score.reasons)

    contacts = await ContactRepository().find_many({"company_id": persist.company_id})
    assert len(contacts) == 1
    assert contacts[0].email == "ada@acme.example"
    assert contacts[0].company_id == persist.company_id

    personalization = CompanyPersonalizationService().generate(lead)
    assert personalization.company_name == "Acme"
    assert personalization.is_flutter_lead is False

    draft = _generated(
        subject="Flutter idea for Acme",
        body="I noticed Acme builds issue tracking tools.",
    )
    ai_generate = AsyncMock(return_value=draft)

    item = await queue.enqueue(
        generated_email=draft,
        company_id=persist.company_id,
        contact_id=str(contacts[0].id),
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
        lead_score=float(score.score),
    )
    assert item.status == EmailQueueStatus.PENDING
    assert item.subject == "Flutter idea for Acme"
    assert "Acme" in item.body

    # Pipeline / scheduler path must not have sent.
    batch = await queue.send_pending()
    assert batch.sent == 0
    assert batch.attempted == 0
    assert (await QueueRepository().find_by_id_item(item.id)).status == EmailQueueStatus.PENDING
    assert transport.call_count == 0

    approved = await queue.approve(item.id)
    assert approved is not None
    assert approved.status == EmailQueueStatus.APPROVED

    ready = await queue.mark_ready_to_send(item.id)
    assert ready is not None
    assert ready.status == EmailQueueStatus.READY_TO_SEND

    with patch("app.ai.service.AIEmailService.generate", ai_generate):
        result = await queue.send_one(item.id)

    assert result.success is True
    assert result.sent == 1
    assert result.status == EmailQueueStatus.SENT
    assert transport.call_count == 1
    assert len(transport.messages) == 1
    message = transport.messages[0]
    assert "ada@acme.example" in str(message["To"])
    assert message["Subject"] == "Flutter idea for Acme"
    assert "I noticed Acme builds issue tracking tools." in message.get_content()
    ai_generate.assert_not_called()

    stored = await QueueRepository().find_by_id_item(item.id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.SENT
    assert stored.sent_at is not None
    assert stored.error_message is None
    assert stored.recipient_email == "ada@acme.example"
    assert stored.company_id == persist.company_id


# ---------------------------------------------------------------------------
# PENDING / APPROVED cannot send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_pending_and_approved_cannot_send(test_db: Any) -> None:
    transport = RecordingTransport()
    queue = EmailQueueService(
        sender=EmailSender(transport=transport, dry_run=False, smtp_enabled=True)
    )

    pending = await queue.enqueue(
        generated_email=_generated(),
        company_id="company-pending",
        contact_id="contact-pending",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    approved = await queue.enqueue(
        generated_email=_generated(subject="Grace"),
        company_id="company-approved",
        contact_id="contact-approved",
        recipient_name="Grace Hopper",
        recipient_email="grace@acme.example",
    )
    await queue.approve(approved.id)

    pending_result = await queue.send_one(pending.id)
    approved_result = await queue.send_one(approved.id)
    batch = await queue.send_ready_to_send()

    assert pending_result.sent == 0 and pending_result.skipped == 1
    assert approved_result.sent == 0 and approved_result.skipped == 1
    assert batch.sent == 0
    assert transport.call_count == 0

    assert (await QueueRepository().find_by_id_item(pending.id)).status == EmailQueueStatus.PENDING
    assert (
        await QueueRepository().find_by_id_item(approved.id)
    ).status == EmailQueueStatus.APPROVED


# ---------------------------------------------------------------------------
# SMTP failure → FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_smtp_failure_marks_failed(test_db: Any) -> None:
    transport = RecordingTransport()
    transport.fail_with = RuntimeError("smtp rejected")
    queue = EmailQueueService(
        sender=EmailSender(transport=transport, dry_run=False, smtp_enabled=True)
    )
    other = await queue.enqueue(
        generated_email=_generated(subject="Other"),
        company_id="company-other",
        contact_id="contact-other",
        recipient_name="Other",
        recipient_email="other@acme.example",
    )

    item_id = await _enqueue_ready(
        queue,
        company_id="company-fail",
        contact_id="contact-fail",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )

    result = await queue.send_one(item_id)
    assert result.success is False
    assert result.failed == 1
    assert result.status == EmailQueueStatus.FAILED
    assert transport.call_count == 1

    stored = await QueueRepository().find_by_id_item(item_id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.FAILED
    assert stored.sent_at is None
    assert "smtp rejected" in (stored.error_message or "")

    untouched = await QueueRepository().find_by_id_item(other.id)
    assert untouched is not None
    assert untouched.status == EmailQueueStatus.PENDING


# ---------------------------------------------------------------------------
# Company isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_company_isolation(test_db: Any) -> None:
    transport = RecordingTransport()
    queue = EmailQueueService(
        sender=EmailSender(transport=transport, dry_run=False, smtp_enabled=True)
    )

    item_a = await queue.enqueue(
        generated_email=_generated(
            subject="Idea for Acme",
            body="Acme React stack note.",
            opening="Hi Ada,",
        ),
        company_id="company-acme",
        contact_id="ada@acme.example",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    item_b = await queue.enqueue(
        generated_email=_generated(
            subject="Idea for NovaLedger",
            body="NovaLedger Next.js note.",
            opening="Hi Sam,",
        ),
        company_id="company-nova",
        contact_id="sam@novaledger.example",
        recipient_name="Sam Ortiz",
        recipient_email="sam@novaledger.example",
    )

    await queue.approve(item_a.id)
    await queue.mark_ready_to_send(item_a.id)
    sent = await queue.send_one(item_a.id)
    assert sent.success is True

    stored_a = await QueueRepository().find_by_id_item(item_a.id)
    stored_b = await QueueRepository().find_by_id_item(item_b.id)
    assert stored_a is not None and stored_b is not None
    assert stored_a.status == EmailQueueStatus.SENT
    assert stored_b.status == EmailQueueStatus.PENDING
    assert stored_a.company_id == "company-acme"
    assert stored_b.company_id == "company-nova"
    assert "NovaLedger" not in stored_a.body
    assert "Acme" not in stored_b.body
    assert stored_a.recipient_email == "ada@acme.example"
    assert stored_b.recipient_email == "sam@novaledger.example"
    assert len(transport.messages) == 1
    assert "ada@acme.example" in str(transport.messages[0]["To"])
    assert "sam@novaledger.example" not in str(transport.messages[0]["To"])


# ---------------------------------------------------------------------------
# Scheduler safety
# ---------------------------------------------------------------------------


def test_e2e_scheduler_timezone_and_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "scheduler_timezone", "Asia/Kolkata")
    monkeypatch.setattr(settings, "scheduler_hour", 9)
    monkeypatch.setattr(settings, "scheduler_minute", 0)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    service = SchedulerService(scheduler=LeadScheduler(scheduler=mock_scheduler))
    service.start()

    assert mock_scheduler.add_job.call_count == 1
    trigger = mock_scheduler.add_job.call_args.kwargs["trigger"]
    assert str(trigger.timezone) == "Asia/Kolkata"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "9"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "0"
    service.shutdown(wait=False)


@pytest.mark.asyncio
async def test_e2e_scheduler_invokes_pipeline_not_send() -> None:
    lead_service = MagicMock()
    report = MagicMock()
    report.success = True
    report.statistics.duration_ms = 1.0
    report.statistics.queued = 1
    report.statistics.processed = 1
    report.statistics.failed = 0
    report.statistics.qualified = 1
    report.statistics.emails_generated = 1
    report.errors = []

    async def _run(**_kwargs: Any) -> Any:
        return report

    lead_service.run = _run
    send_pending = AsyncMock()
    send_one = AsyncMock()
    send_ready = AsyncMock()

    with (
        patch("app.email_queue.service.EmailQueueService.send_pending", send_pending),
        patch("app.email_queue.service.EmailQueueService.send_one", send_one),
        patch("app.email_queue.service.EmailQueueService.send_ready_to_send", send_ready),
        patch("app.email.smtp_client.SmtpClient.send_message", MagicMock()) as smtp_send,
        patch("app.email_queue.approval.ApprovalService.approve", AsyncMock()) as approve,
    ):
        result = await DailyLeadGenerationJob(lead_generation_service=lead_service).execute()

    assert result.success is True
    assert "run_id" in result.details
    send_pending.assert_not_called()
    send_one.assert_not_called()
    send_ready.assert_not_called()
    smtp_send.assert_not_called()
    approve.assert_not_called()


# ---------------------------------------------------------------------------
# Daily logging + retention
# ---------------------------------------------------------------------------


def test_e2e_daily_logging_writes_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.email.smtp_client import sanitize_smtp_error_message

    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    detach_daily_run_handler()
    path = ensure_daily_run_handler(log_dir=tmp_path)
    assert path is not None
    assert path.name.endswith("logs.txt")
    assert daily_log_filename(date.today()) == path.name

    logger = get_logger("e2e_daily")
    with caplog.at_level(logging.INFO):
        logger.info("[SCHEDULER] Scheduler started")
        logger.info("[PIPELINE] Starting run_id=test-run")
        logger.info("[EMAIL] sent queue_id=q1 recipient=ada@acme.example")
        # App sanitizer must never emit the raw password.
        safe = sanitize_smtp_error_message(
            RuntimeError(f"auth failed for {settings.smtp_password}")
        )
        logger.info("[EMAIL] send_failed queue_id=q1 reason=%s", safe)

    text = path.read_text(encoding="utf-8")
    assert "[SCHEDULER] Scheduler started" in text
    assert "[PIPELINE] Starting run_id=test-run" in text
    assert "[EMAIL] sent queue_id=q1" in text
    assert "[EMAIL] send_failed" in text
    assert "super-secret-e2e-password" not in text
    assert "***" in text
    assert "I noticed Acme builds" not in text
    detach_daily_run_handler()


def test_e2e_log_retention_keeps_configured_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_retention_days", 7)
    start = date(2026, 8, 1)
    for offset in range(10):
        day = start + timedelta(days=offset)
        (tmp_path / daily_log_filename(day)).write_text(f"{day}\n", encoding="utf-8")
    unrelated = tmp_path / "app.log"
    unrelated.write_text("keep\n", encoding="utf-8")
    notes = tmp_path / "notes.txt"
    notes.write_text("keep\n", encoding="utf-8")

    prune_daily_logs(tmp_path)
    remaining = list_daily_log_files(tmp_path)
    assert len(remaining) == 7
    assert remaining[0].name == "2026-08-04logs.txt"
    assert remaining[-1].name == "2026-08-10logs.txt"
    assert unrelated.exists()
    assert notes.exists()


# ---------------------------------------------------------------------------
# Pipeline run does not auto-send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_pipeline_run_does_not_send(
    test_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = RecordingTransport()
    real_queue = EmailQueueService(
        sender=EmailSender(transport=transport, dry_run=False, smtp_enabled=True)
    )
    send_pending = AsyncMock(wraps=real_queue.send_pending)
    send_one = AsyncMock(wraps=real_queue.send_one)
    send_ready = AsyncMock(wraps=real_queue.send_ready_to_send)
    real_queue.send_pending = send_pending  # type: ignore[method-assign]
    real_queue.send_one = send_one  # type: ignore[method-assign]
    real_queue.send_ready_to_send = send_ready  # type: ignore[method-assign]

    harness = build_orchestrator(email_queue_service=real_queue)
    harness.orchestrator.collection_service.collect_all = AsyncMock(
        return_value=make_collection_report(count=1)
    )
    # Persist into mongomock via real persistence for one lead.
    lead = make_lead(company_name="Company 1")
    harness.orchestrator.pipeline_service.process = AsyncMock(return_value=lead)
    harness.orchestrator.persistence_service = PipelinePersistenceService()

    monkeypatch.setattr(
        "app.lead_generation.service.ensure_mongo_ready",
        AsyncMock(),
    )
    monkeypatch.setattr(settings, "log_dir", str(Path.cwd() / "logs"))

    service = LeadGenerationService(orchestrator=harness.orchestrator)
    report = await service.run(limit=1, persist=True, generate_emails=True, enqueue_emails=True)

    assert report.statistics.queued >= 1
    send_pending.assert_not_called()
    send_one.assert_not_called()
    send_ready.assert_not_called()
    assert transport.call_count == 0

    pending_items = await QueueRepository().get_pending()
    assert len(pending_items) >= 1
    assert all(item.status == EmailQueueStatus.PENDING for item in pending_items)


# ---------------------------------------------------------------------------
# Approval transition rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_approval_flow_and_invalid_transitions(test_db: Any) -> None:
    queue = EmailQueueService(sender=EmailSender(dry_run=True))
    approval = ApprovalService()
    item = await queue.enqueue(
        generated_email=_generated(),
        company_id="company-flow",
        contact_id="contact-flow",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )

    assert can_transition(EmailQueueStatus.PENDING, EmailQueueStatus.SENT) is False
    assert can_transition(EmailQueueStatus.APPROVED, EmailQueueStatus.SENT) is False
    assert can_transition(EmailQueueStatus.READY_TO_SEND, EmailQueueStatus.SENT) is True

    with pytest.raises(InvalidTransitionError):
        await approval.mark_sent(item.id)

    approved = await queue.approve(item.id)
    assert approved is not None and approved.status == EmailQueueStatus.APPROVED
    with pytest.raises(InvalidTransitionError):
        await approval.mark_sent(item.id)

    ready = await queue.mark_ready_to_send(item.id)
    assert ready is not None and ready.status == EmailQueueStatus.READY_TO_SEND

    sent = await queue.send_one(item.id)
    assert sent.success is True
    assert sent.status == EmailQueueStatus.SENT
    stored = await QueueRepository().find_by_id_item(item.id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.SENT
