"""Step 38 approval transition gate tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.types import GeneratedEmail
from app.email_queue.approval import ApprovalService
from app.email_queue.service import EmailQueueService
from app.email_queue.transitions import InvalidTransitionError, can_transition
from app.email_queue.types import EmailQueueStatus
from tests.test_lead_generation import build_orchestrator


def make_email() -> GeneratedEmail:
    return GeneratedEmail(
        subject="Hello",
        opening="Hi,",
        body="Body",
        cta="Call?",
        generation_source="fallback",
    )


@pytest.mark.asyncio
async def test_pending_to_approved(test_db: Any) -> None:
    service = ApprovalService()
    item = await EmailQueueService().enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    updated = await service.approve(item.id)
    assert updated.status == EmailQueueStatus.APPROVED


@pytest.mark.asyncio
async def test_pending_to_skipped(test_db: Any) -> None:
    service = ApprovalService()
    item = await EmailQueueService().enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    updated = await service.skip(item.id)
    assert updated.status == EmailQueueStatus.SKIPPED


@pytest.mark.asyncio
async def test_approved_to_ready_to_send(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    ready = await ApprovalService().mark_ready_to_send(item.id)
    assert ready.status == EmailQueueStatus.READY_TO_SEND


@pytest.mark.asyncio
async def test_ready_to_send_to_sent(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    await queue.mark_ready_to_send(item.id)
    sent = await ApprovalService().mark_sent(item.id)
    assert sent.status == EmailQueueStatus.SENT


@pytest.mark.asyncio
async def test_ready_to_send_to_failed(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    await queue.mark_ready_to_send(item.id)
    failed = await ApprovalService().mark_failed(item.id, error="boom")
    assert failed.status == EmailQueueStatus.FAILED


@pytest.mark.asyncio
async def test_sent_to_pending_rejected(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    await queue.mark_ready_to_send(item.id)
    await ApprovalService().mark_sent(item.id)
    with pytest.raises(InvalidTransitionError):
        await ApprovalService().approve(item.id)


@pytest.mark.asyncio
async def test_sent_to_approved_rejected(test_db: Any) -> None:
    assert can_transition(EmailQueueStatus.SENT, EmailQueueStatus.APPROVED) is False
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    await queue.mark_ready_to_send(item.id)
    await ApprovalService().mark_sent(item.id)
    with pytest.raises(InvalidTransitionError):
        await ApprovalService().approve(item.id)


@pytest.mark.asyncio
async def test_failed_to_sent_rejected(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.approve(item.id)
    await queue.mark_ready_to_send(item.id)
    await ApprovalService().mark_failed(item.id, error="boom")
    with pytest.raises(InvalidTransitionError):
        await ApprovalService().mark_sent(item.id)


@pytest.mark.asyncio
async def test_skipped_to_ready_to_send_rejected(test_db: Any) -> None:
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    await queue.skip(item.id)
    with pytest.raises(InvalidTransitionError):
        await ApprovalService().mark_ready_to_send(item.id)


@pytest.mark.asyncio
async def test_pending_cannot_become_sent_directly(test_db: Any) -> None:
    assert can_transition(EmailQueueStatus.PENDING, EmailQueueStatus.SENT) is False
    queue = EmailQueueService()
    item = await queue.enqueue(
        generated_email=make_email(),
        company_id="c1",
        contact_id="t1",
        recipient_name="Ada",
        recipient_email="ada@acme.example",
    )
    with pytest.raises(InvalidTransitionError):
        await ApprovalService().mark_sent(item.id)
    result = await queue.send_one(item.id)
    assert result.skipped == 1
    assert result.sent == 0


@pytest.mark.asyncio
async def test_pipeline_leaves_queue_pending_without_auto_approval() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=1)
    assert report.statistics.queued == 1
    harness.enqueue_mock.assert_called_once()
    # Enqueue path still creates PENDING — approval is never auto-applied.
    call_kwargs = harness.enqueue_mock.await_args.kwargs
    assert "generated_email" in call_kwargs
