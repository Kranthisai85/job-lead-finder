from __future__ import annotations

from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.ai.types import GeneratedEmail
from app.email_queue.document import EmailQueueEntry
from app.email_queue.repository import QueueRepository
from app.email_queue.sender import EmailSender
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueStatus


@pytest.fixture()
async def queue_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_test"]
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
        self.fail_next = False

    def send_message(self, message: Any) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("smtp failure")
        self.messages.append(message)


@pytest.mark.asyncio
async def test_enqueue_creates_pending_item(queue_db: Any) -> None:
    service = EmailQueueService()
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
        lead_score=82.5,
    )

    assert item.status == EmailQueueStatus.PENDING
    assert item.subject == "Flutter idea for Acme"
    assert "Hi Ada," in item.body
    assert item.generation_source == "fallback"
    assert item.lead_score == 82.5


@pytest.mark.asyncio
async def test_approval_workflow(queue_db: Any) -> None:
    service = EmailQueueService()
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )

    approved = await service.approve(item.id)
    assert approved is not None
    assert approved.status == EmailQueueStatus.APPROVED
    assert approved.approved_at is not None

    rejected = await service.reject(item.id, reason="Not a fit")
    assert rejected is not None
    assert rejected.status == EmailQueueStatus.CANCELLED
    assert rejected.error_message == "Not a fit"


@pytest.mark.asyncio
async def test_dry_run_send_marks_sent(queue_db: Any) -> None:
    sender = EmailSender(dry_run=True)
    service = EmailQueueService(sender=sender)
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    await service.approve(item.id)

    result = await service.send_pending()
    assert result.sent == 1
    assert result.failed == 0

    stats = await service.statistics()
    assert stats.sent == 1
    assert stats.approved == 0


@pytest.mark.asyncio
async def test_send_one_success(queue_db: Any) -> None:
    transport = StubTransport()
    sender = EmailSender(transport=transport, dry_run=False)
    service = EmailQueueService(sender=sender)
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    await service.approve(item.id)

    result = await service.send_one(item.id)
    assert result.sent == 1
    assert len(transport.messages) == 1


@pytest.mark.asyncio
async def test_send_failure_and_retry(queue_db: Any) -> None:
    transport = StubTransport()
    transport.fail_next = True
    sender = EmailSender(transport=transport, dry_run=False)
    service = EmailQueueService(sender=sender)
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    await service.approve(item.id)

    first = await service.send_one(item.id)
    assert first.failed == 1

    failed_entry = await QueueRepository().find_by_id_item(item.id)
    assert failed_entry is not None
    assert failed_entry.status == EmailQueueStatus.FAILED
    assert failed_entry.retry_count == 1

    second = await service.send_one(item.id)
    assert second.sent == 1

    sent_entry = await QueueRepository().find_by_id_item(item.id)
    assert sent_entry is not None
    assert sent_entry.status == EmailQueueStatus.SENT


@pytest.mark.asyncio
async def test_max_retry_limit(queue_db: Any) -> None:
    transport = StubTransport()
    sender = EmailSender(transport=transport, dry_run=False)
    sender.send = AsyncMock(side_effect=RuntimeError("smtp down"))  # type: ignore[method-assign]
    service = EmailQueueService(sender=sender)
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    await service.approve(item.id)

    for _ in range(3):
        await service.send_one(item.id)

    blocked = await service.send_one(item.id)
    assert blocked.skipped == 1
    assert "max retries" in blocked.errors[0].lower()

    entry = await QueueRepository().find_by_id_item(item.id)
    assert entry is not None
    assert entry.retry_count == 3


@pytest.mark.asyncio
async def test_statistics(queue_db: Any) -> None:
    service = EmailQueueService()
    item = await service.enqueue(
        generated_email=make_generated_email(),
        company_id="company-1",
        contact_id="contact-1",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
    )
    await service.approve(item.id)
    await service.send_pending()

    stats = await service.statistics()
    assert stats.total == 1
    assert stats.sent == 1
    assert stats.pending == 0


@pytest.mark.asyncio
async def test_repository_get_pending_and_approved(queue_db: Any) -> None:
    repo = QueueRepository()
    await repo.create(
        {
            "company_id": "c1",
            "contact_id": "t1",
            "recipient_name": "A",
            "recipient_email": "a@example.com",
            "subject": "S",
            "body": "B",
            "status": EmailQueueStatus.PENDING,
        }
    )
    approved_entry = await repo.create(
        {
            "company_id": "c2",
            "contact_id": "t2",
            "recipient_name": "B",
            "recipient_email": "b@example.com",
            "subject": "S2",
            "body": "B2",
            "status": EmailQueueStatus.APPROVED,
        }
    )

    pending = await repo.get_pending()
    approved = await repo.get_approved()
    assert len(pending) == 1
    assert len(approved) == 1
    assert str(approved[0].id) == str(approved_entry.id)
