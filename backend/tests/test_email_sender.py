"""Step 40 — SMTP delivery tests (mocked transport only; never real SMTP)."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.ai.types import GeneratedEmail
from app.core.config import Settings, settings
from app.email.exceptions import (
    SmtpAuthenticationError,
    SmtpConnectionError,
    SmtpDisabledError,
    SmtpTimeoutError,
)
from app.email.message import build_email_message
from app.email.sender import EmailSender
from app.email.smtp_client import SmtpClient, sanitize_smtp_error_message
from app.email_queue.document import EmailQueueEntry
from app.email_queue.repository import QueueRepository
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueStatus
from app.scheduler.jobs import DailyLeadGenerationJob


@pytest.fixture()
async def queue_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_smtp_test"]
    await init_beanie(database=database, document_models=[EmailQueueEntry])
    yield database
    await EmailQueueEntry.delete_all()
    client.close()


def make_generated_email() -> GeneratedEmail:
    return GeneratedEmail(
        subject="Flutter idea for Acme",
        opening="Hi Ada,",
        body="I noticed Acme uses React.",
        cta="Open to a quick call?",
        generation_source="fallback",
    )


class StubTransport:
    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.fail_with: Exception | None = None

    def send_message(self, message: Any) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.messages.append(message)


async def _ready_item(service: EmailQueueService, **kwargs: Any) -> str:
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id=kwargs.get("company_id", "company-1"),
        contact_id=kwargs.get("contact_id", "contact-1"),
        recipient_name=kwargs.get("recipient_name", "Ada Lovelace"),
        recipient_email=kwargs.get("recipient_email", "ada@acme.example"),
    )
    await service.approve(item.id)
    await service.mark_ready_to_send(item.id)
    return item.id


def test_smtp_defaults() -> None:
    cfg = Settings(
        _env_file=None,  # type: ignore[call-arg]
        smtp_enabled=False,
        smtp_host="",
        smtp_port=587,
        smtp_use_tls=True,
        dry_run=True,
    )
    assert cfg.smtp_enabled is False
    assert cfg.smtp_port == 587
    assert cfg.effective_smtp_use_tls is True
    assert cfg.smtp_timeout_seconds == 30.0


def test_smtp_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "out@example.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Lead Finder")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "45")
    cfg = Settings(_env_file=None)  # type: ignore[call-arg]
    assert cfg.smtp_enabled is True
    assert cfg.smtp_host == "smtp.example.com"
    assert cfg.smtp_port == 465
    assert cfg.smtp_from_email == "out@example.com"
    assert cfg.smtp_from_name == "Lead Finder"
    assert cfg.smtp_timeout_seconds == 45.0


def test_build_email_message_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_from_email", "from@example.com")
    monkeypatch.setattr(settings, "smtp_from_name", "Lead Finder")
    monkeypatch.setattr(settings, "smtp_reply_to", "reply@example.com")
    monkeypatch.setattr(settings, "from_email", "")

    message = build_email_message(
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
        subject="Hello",
        body="Body text",
    )
    assert "from@example.com" in message["From"]
    assert "Lead Finder" in message["From"]
    assert "ada@acme.example" in message["To"]
    assert message["Subject"] == "Hello"
    assert message["Reply-To"] == "reply@example.com"
    assert "Body text" in message.get_content()


def test_smtp_client_success_with_tls_and_auth() -> None:
    fake_smtp = MagicMock()
    message = build_email_message(
        recipient_email="ada@acme.example",
        subject="S",
        body="B",
        from_email="from@example.com",
    )
    with patch("app.email.smtp_client.smtplib.SMTP", return_value=fake_smtp) as smtp_ctor:
        fake_smtp.__enter__ = MagicMock(return_value=fake_smtp)
        fake_smtp.__exit__ = MagicMock(return_value=False)
        # SmtpClient does not use context manager — instantiate then quit
        smtp_ctor.return_value = fake_smtp
        client = SmtpClient(
            host="smtp.example.com",
            port=587,
            username="user",
            password="secret",
            use_tls=True,
            timeout_seconds=12,
        )
        client.send_message(message)

    smtp_ctor.assert_called_once_with("smtp.example.com", 587, timeout=12)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("user", "secret")
    fake_smtp.send_message.assert_called_once_with(message)
    fake_smtp.quit.assert_called_once()


def test_smtp_client_connection_failure() -> None:
    with patch(
        "app.email.smtp_client.smtplib.SMTP",
        side_effect=ConnectionError("refused"),
    ):
        client = SmtpClient(host="smtp.example.com", port=587, use_tls=False)
        with pytest.raises(SmtpConnectionError):
            client.send_message(
                build_email_message(
                    recipient_email="a@b.co",
                    subject="S",
                    body="B",
                    from_email="from@example.com",
                )
            )


def test_smtp_client_authentication_failure() -> None:
    fake_smtp = MagicMock()
    import smtplib

    fake_smtp.starttls.return_value = None
    fake_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
    with patch("app.email.smtp_client.smtplib.SMTP", return_value=fake_smtp):
        client = SmtpClient(
            host="smtp.example.com",
            username="user",
            password="secret",
            use_tls=True,
        )
        with pytest.raises(SmtpAuthenticationError, match="authentication failed"):
            client.send_message(
                build_email_message(
                    recipient_email="a@b.co",
                    subject="S",
                    body="B",
                    from_email="from@example.com",
                )
            )


def test_smtp_client_timeout() -> None:
    with patch(
        "app.email.smtp_client.smtplib.SMTP",
        side_effect=TimeoutError("timed out"),
    ):
        client = SmtpClient(host="smtp.example.com", use_tls=False)
        with pytest.raises(SmtpTimeoutError):
            client.send_message(
                build_email_message(
                    recipient_email="a@b.co",
                    subject="S",
                    body="B",
                    from_email="from@example.com",
                )
            )


@pytest.mark.asyncio
async def test_email_sender_disabled_without_transport() -> None:
    sender = EmailSender(dry_run=False, smtp_enabled=False)
    with pytest.raises(SmtpDisabledError):
        await sender.send(
            recipient_name="Ada",
            recipient_email="ada@acme.example",
            subject="S",
            body="B",
        )


@pytest.mark.asyncio
async def test_ready_to_send_success_marks_sent(queue_db: Any) -> None:
    transport = StubTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    item_id = await _ready_item(service)

    result = await service.send_one(item_id)
    assert result.success is True
    assert result.sent == 1
    assert result.status == EmailQueueStatus.SENT
    assert result.queue_id == item_id
    assert len(transport.messages) == 1

    stored = await QueueRepository().find_by_id_item(item_id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.SENT
    assert stored.sent_at is not None

    second = await service.send_one(item_id)
    assert second.skipped == 1
    assert len(transport.messages) == 1


@pytest.mark.asyncio
async def test_ready_to_send_smtp_failure_marks_failed(queue_db: Any) -> None:
    transport = StubTransport()
    transport.fail_with = RuntimeError("smtp boom")
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    item_id = await _ready_item(service)

    result = await service.send_one(item_id)
    assert result.success is False
    assert result.failed == 1
    assert result.status == EmailQueueStatus.FAILED
    assert "smtp boom" in (result.error or "")

    stored = await QueueRepository().find_by_id_item(item_id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.FAILED
    assert stored.sent_at is None


@pytest.mark.asyncio
async def test_state_safety_only_ready_to_send_invokes_smtp(queue_db: Any) -> None:
    transport = StubTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))

    pending = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    approved = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="c2",
        contact_id="t2",
        recipient_name="Grace",
        recipient_email="grace@acme.example",
    )
    await service.approve(approved.id)

    for item_id in (pending.id, approved.id):
        result = await service.send_one(item_id)
        assert result.skipped == 1
        assert result.sent == 0

    assert transport.messages == []

    ready_id = await _ready_item(service, company_id="c3", contact_id="t3")
    await service.send_one(ready_id)
    assert len(transport.messages) == 1

    # SENT cannot send again
    again = await service.send_one(ready_id)
    assert again.skipped == 1

    # FAILED cannot send again
    fail_transport = StubTransport()
    fail_transport.fail_with = RuntimeError("nope")
    fail_service = EmailQueueService(sender=EmailSender(transport=fail_transport, dry_run=False))
    failed_id = await _ready_item(
        fail_service, company_id="c4", contact_id="t4", recipient_email="f@acme.example"
    )
    await fail_service.send_one(failed_id)
    blocked = await fail_service.send_one(failed_id)
    assert blocked.skipped == 1
    assert fail_transport.messages == []


@pytest.mark.asyncio
async def test_batch_isolates_failures(queue_db: Any) -> None:
    class SelectiveTransport:
        def __init__(self) -> None:
            self.messages: list[Any] = []

        def send_message(self, message: Any) -> None:
            to_header = str(message["To"])
            if "bad@" in to_header:
                raise RuntimeError("recipient rejected")
            self.messages.append(message)

    transport = SelectiveTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    good_a = await _ready_item(
        service, company_id="a", contact_id="a", recipient_email="good1@acme.example"
    )
    bad = await _ready_item(
        service, company_id="b", contact_id="b", recipient_email="bad@acme.example"
    )
    good_b = await _ready_item(
        service, company_id="c", contact_id="c", recipient_email="good2@acme.example"
    )

    result = await service.send_ready_to_send()
    assert result.attempted == 3
    assert result.sent == 2
    assert result.failed == 1
    assert len(transport.messages) == 2

    assert (await QueueRepository().find_by_id_item(good_a)).status == EmailQueueStatus.SENT
    assert (await QueueRepository().find_by_id_item(bad)).status == EmailQueueStatus.FAILED
    assert (await QueueRepository().find_by_id_item(good_b)).status == EmailQueueStatus.SENT


@pytest.mark.asyncio
async def test_invalid_recipient_skips_smtp(queue_db: Any) -> None:
    transport = StubTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    item_id = await _ready_item(service)
    entry = await QueueRepository().find_by_id_item(item_id)
    assert entry is not None
    entry.recipient_email = "not-an-email"
    await entry.save()

    result = await service.send_one(item_id)
    assert result.failed == 1
    assert transport.messages == []
    stored = await QueueRepository().find_by_id_item(item_id)
    assert stored is not None
    assert stored.status == EmailQueueStatus.FAILED
    assert "Invalid recipient" in (stored.error_message or "")


@pytest.mark.asyncio
async def test_scheduler_does_not_send_email(queue_db: Any) -> None:
    transport = StubTransport()
    report = MagicMock()
    report.success = True
    report.statistics.duration_ms = 1.0
    report.statistics.queued = 0
    report.statistics.processed = 0
    report.statistics.failed = 0
    report.statistics.qualified = 0
    report.statistics.emails_generated = 0
    report.errors = []

    lead_service = MagicMock()

    async def _run(**_kwargs: Any) -> Any:
        return report

    lead_service.run = _run
    job = DailyLeadGenerationJob(lead_generation_service=lead_service)
    await job.execute()
    assert transport.messages == []


@pytest.mark.asyncio
async def test_send_logging_omits_password_and_body(
    queue_db: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "smtp_password", "super-secret-password")
    transport = StubTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    item_id = await _ready_item(service)

    with caplog.at_level(logging.INFO):
        await service.send_one(item_id)

    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "[EMAIL] send_started" in joined
    assert "[EMAIL] sent" in joined
    assert "super-secret-password" not in joined
    assert "I noticed Acme uses React" not in joined


@pytest.mark.asyncio
async def test_send_failure_logging(
    queue_db: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "smtp_password", "super-secret-password")
    transport = StubTransport()
    transport.fail_with = RuntimeError("boom with super-secret-password leaked")
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    item_id = await _ready_item(service)

    with caplog.at_level(logging.ERROR):
        await service.send_one(item_id)

    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "[EMAIL] send_failed" in joined
    assert "super-secret-password" not in joined
    assert "***" in sanitize_smtp_error_message(
        RuntimeError("boom with super-secret-password leaked")
    )


@pytest.mark.asyncio
async def test_pending_never_invokes_smtp_transport(queue_db: Any) -> None:
    transport = StubTransport()
    service = EmailQueueService(sender=EmailSender(transport=transport, dry_run=False))
    await service.enqueue(
        generated_email=make_generated_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    result = await service.send_ready_to_send()
    assert result.attempted == 0
    assert result.sent == 0
    assert transport.messages == []
