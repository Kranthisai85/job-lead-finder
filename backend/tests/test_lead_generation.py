from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict, Unpack
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.types import GeneratedEmail
from app.collectors.types import CompanyLead
from app.email_queue.types import EmailQueueItem, EmailQueueStatus
from app.lead_generation.orchestrator import LeadGenerationOrchestrator
from app.lead_generation.service import LeadGenerationService
from app.lead_generation.statistics import build_statistics, format_run_summary
from app.lead_generation.types import (
    LeadGenerationReport,
    LeadGenerationResult,
    LeadGenerationStatistics,
    StageTiming,
)
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.persistence_types import PersistenceResult
from app.source_manager.types import SourceCollectionReport
from tests.test_personalization import make_lead


def make_collection_report(*, count: int = 2) -> SourceCollectionReport:
    companies = [
        CompanyLead(
            name=f"Company {index}",
            website=f"https://company{index}.example",
            description=f"Description {index}",
            source="test",
        )
        for index in range(1, count + 1)
    ]
    return SourceCollectionReport(
        collectors_run=["test"],
        total_found=count,
        unique_companies=companies,
        execution_time_ms=12.5,
    )


def make_generated_email() -> GeneratedEmail:
    return GeneratedEmail(
        subject="Hello from Lead Finder",
        opening="Hi there,",
        body="We noticed your product.",
        cta="Open to a quick call?",
        generation_source="fallback",
    )


def make_personalization() -> PersonalizedEmailContext:
    return PersonalizedEmailContext(
        company_name="Acme",
        company_summary="Acme builds issue tracking tools.",
        personalized_opening="Congrats on the launch.",
        mobile_app_opportunity="No mobile app detected.",
        technologies_summary="React, Tailwind",
        qualification_summary="Qualified lead.",
        suggested_value_proposition="Flutter could help.",
        cta_recommendation="Offer a short intro call.",
        confidence_score=0.9,
        is_flutter_lead=True,
        has_mobile_app=False,
        technology_names=["React", "Tailwind"],
    )


def make_queue_item() -> EmailQueueItem:
    return EmailQueueItem(
        id="queue-1",
        company_id="company-1",
        contact_id="ada@acme.example",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
        subject="Hello from Lead Finder",
        body="Hi there,\n\nWe noticed your product.",
        status=EmailQueueStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        generation_source="fallback",
        lead_score=88.0,
    )


class OrchestratorOverrides(TypedDict, total=False):
    collection_service: AsyncMock
    persistence_service: AsyncMock
    pipeline_service: AsyncMock
    personalization_service: MagicMock
    ai_email_service: AsyncMock
    email_queue_service: AsyncMock


@dataclass(frozen=True)
class LeadGenerationTestHarness:
    orchestrator: LeadGenerationOrchestrator
    persist_mock: AsyncMock
    ai_generate_mock: AsyncMock
    enqueue_mock: AsyncMock


def build_orchestrator(**overrides: Unpack[OrchestratorOverrides]) -> LeadGenerationTestHarness:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report())

    persist_mock = AsyncMock(
        return_value=PersistenceResult(
            company_id="company-1",
            company_created=True,
            contacts_created=1,
            duration_ms=5.0,
        )
    )
    persistence_service = AsyncMock()
    persistence_service.persist = persist_mock

    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(side_effect=lambda seed: make_lead(company_name=seed.name))

    personalization_service = MagicMock()
    personalization_service.generate = MagicMock(return_value=make_personalization())

    ai_generate_mock = AsyncMock(return_value=make_generated_email())
    ai_email_service = AsyncMock()
    ai_email_service.generate = ai_generate_mock

    enqueue_mock = AsyncMock(return_value=make_queue_item())
    email_queue_service = AsyncMock()
    email_queue_service.enqueue = enqueue_mock
    email_queue_service.is_duplicate_company = AsyncMock(return_value=False)
    email_queue_service.is_duplicate_recipient = AsyncMock(return_value=False)

    services: OrchestratorOverrides = {
        "collection_service": collection_service,
        "persistence_service": persistence_service,
        "pipeline_service": pipeline_service,
        "personalization_service": personalization_service,
        "ai_email_service": ai_email_service,
        "email_queue_service": email_queue_service,
    }
    services.update(overrides)

    orchestrator = LeadGenerationOrchestrator(**services)
    return LeadGenerationTestHarness(
        orchestrator=orchestrator,
        persist_mock=services["persistence_service"].persist,
        ai_generate_mock=services["ai_email_service"].generate,
        enqueue_mock=services["email_queue_service"].enqueue,
    )


@pytest.mark.asyncio
async def test_successful_run() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=2)

    assert report.success is True
    assert report.statistics.total_collected == 2
    assert report.statistics.processed == 2
    assert report.statistics.persisted == 2
    assert report.statistics.qualified == 2
    assert report.statistics.emails_generated == 2
    assert report.statistics.queued == 2
    assert report.statistics.failed == 0
    assert report.statistics.duration_ms >= 0
    assert len(report.stage_timings) == 1
    assert report.stage_timings[0].stage == "collect"
    assert report.stage_timings[0].duration_ms >= 0

    for result in report.results:
        assert result.success is True
        assert result.persisted is True
        assert result.email_generated is True
        assert result.queued is True
        assert result.duration_ms >= 0
        assert any(timing.stage == "pipeline" for timing in result.stage_timings)
        assert any(timing.stage == "persist" for timing in result.stage_timings)
        assert any(timing.stage == "personalization" for timing in result.stage_timings)
        assert any(timing.stage == "ai_email" for timing in result.stage_timings)
        assert any(timing.stage == "enqueue" for timing in result.stage_timings)


@pytest.mark.asyncio
async def test_runtime_stage_logs_are_emitted(caplog: pytest.LogCaptureFixture) -> None:
    harness = build_orchestrator()
    with caplog.at_level("INFO"):
        await harness.orchestrator.run(limit=1)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "[PIPELINE] Starting lead generation run" in messages
    assert "[PIPELINE] Processing company=" in messages
    assert "[QUALIFICATION] company=" in messages
    assert "status=" in messages
    assert "eligible=" in messages
    assert "reasons=" in messages
    assert "[FLUTTER] company=" in messages
    assert "[PERSONALIZATION] company=" in messages
    assert "completed" in messages
    assert "[AI] company=" in messages and "generation_started" in messages
    assert "[AI] company=" in messages and "source=" in messages
    assert "[QUEUE] company=" in messages and "status=PENDING" in messages
    assert "[PIPELINE] Completed discovered=" in messages
    assert "[RUN SUMMARY] Fetched (raw from sources):" in messages
    assert "[RUN SUMMARY] Qualified:" in messages
    assert "[RUN SUMMARY] Shortlisted / queued:" in messages
    assert "[FUNNEL] collected=" in messages


@pytest.mark.asyncio
async def test_empty_sources() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(
        return_value=SourceCollectionReport(unique_companies=[])
    )
    harness = build_orchestrator(collection_service=collection_service)
    report = await harness.orchestrator.run()

    assert report.statistics.total_collected == 0
    assert report.statistics.processed == 0
    assert report.results == []
    assert "No startup seeds collected" in report.warnings


@pytest.mark.asyncio
async def test_ai_disabled() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=1, generate_emails=False, enqueue_emails=False)

    assert report.statistics.emails_generated == 0
    assert report.statistics.queued == 0
    assert report.results[0].email_generated is False
    assert report.results[0].queued is False
    harness.ai_generate_mock.assert_not_called()
    harness.enqueue_mock.assert_not_called()


@pytest.mark.asyncio
async def test_queue_disabled() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=1, enqueue_emails=False)

    assert report.statistics.emails_generated == 1
    assert report.statistics.queued == 0
    assert report.results[0].email_generated is True
    assert report.results[0].queued is False
    harness.enqueue_mock.assert_not_called()


@pytest.mark.asyncio
async def test_persist_disabled() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=1, persist=False)

    assert report.statistics.persisted == 0
    assert report.results[0].persisted is False
    harness.persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_persist_soft_failure_surfaces_real_error() -> None:
    persist_mock = AsyncMock(
        return_value=PersistenceResult(
            company_id=None,
            errors=["company persistence failed (mongodb): ServerSelectionTimeoutError: timeout"],
            duration_ms=1.0,
        )
    )
    persistence_service = AsyncMock()
    persistence_service.persist = persist_mock
    harness = build_orchestrator(persistence_service=persistence_service)
    report = await harness.orchestrator.run(limit=1, generate_emails=False, enqueue_emails=False)

    assert report.results[0].success is False
    assert report.results[0].persisted is False
    assert "ServerSelectionTimeoutError" in report.results[0].errors[0]
    assert "Persistence failed" not in report.results[0].errors[0]
    persist_timing = next(
        timing for timing in report.results[0].stage_timings if timing.stage == "persist"
    )
    assert persist_timing.success is False
    assert "ServerSelectionTimeoutError" in (persist_timing.error or "")


@pytest.mark.asyncio
async def test_persist_raised_empty_exception_includes_type_name() -> None:
    persist_mock = AsyncMock(side_effect=RuntimeError())
    persistence_service = AsyncMock()
    persistence_service.persist = persist_mock
    harness = build_orchestrator(persistence_service=persistence_service)
    report = await harness.orchestrator.run(limit=1, generate_emails=False, enqueue_emails=False)

    assert report.results[0].success is False
    assert "RuntimeError" in report.results[0].errors[0]
    assert "Persistence failed" not in report.results[0].errors[0]
    persist_timing = next(
        timing for timing in report.results[0].stage_timings if timing.stage == "persist"
    )
    assert persist_timing.success is False
    assert "RuntimeError" in (persist_timing.error or "")


@pytest.mark.asyncio
async def test_exception_during_one_company_continues() -> None:
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(
        side_effect=[
            make_lead(company_name="Company 1"),
            RuntimeError("pipeline exploded"),
        ]
    )
    harness = build_orchestrator(pipeline_service=pipeline_service)
    report = await harness.orchestrator.run(limit=2)

    assert report.statistics.processed == 2
    assert report.statistics.failed == 1
    assert report.results[0].success is True
    assert report.results[1].success is False
    assert "pipeline exploded" in report.results[1].errors[0]
    harness.ai_generate_mock.assert_called_once()


@pytest.mark.asyncio
async def test_statistics_aggregation() -> None:
    results = [
        LeadGenerationResult(
            company_name="A",
            website="https://a.example",
            success=True,
            persisted=True,
            qualified=True,
            email_generated=True,
            queued=True,
        ),
        LeadGenerationResult(
            company_name="B",
            website="https://b.example",
            success=False,
            persisted=False,
            qualified=False,
            email_generated=False,
            queued=False,
        ),
    ]
    stats = build_statistics(results, total_collected=2, duration_ms=123.45)

    assert stats.total_collected == 2
    assert stats.processed == 2
    assert stats.persisted == 1
    assert stats.qualified == 1
    assert stats.emails_generated == 1
    assert stats.queued == 1
    assert stats.failed == 1
    assert stats.duration_ms == 123.45


def test_format_run_summary_includes_funnel_labels() -> None:
    summary = format_run_summary(
        LeadGenerationStatistics(
            total_collected=10,
            processed=10,
            persisted=8,
            qualified=5,
            emails_generated=4,
            queued=3,
            failed=1,
            skipped_duplicate=2,
            skipped_no_recipient=1,
            duration_ms=1500,
        ),
        total_found=20,
        unique_companies=12,
        duplicates_removed=8,
        personalized=4,
        success=True,
    )
    assert "Fetched (raw from sources):     20" in summary
    assert "Selected for pipeline:          10" in summary
    assert "Qualified:                      5" in summary
    assert "Shortlisted / queued:           3" in summary
    assert "Status:                         SUCCESS" in summary


@pytest.mark.asyncio
async def test_timing_populated() -> None:
    harness = build_orchestrator()
    report = await harness.orchestrator.run(limit=1)

    assert report.statistics.duration_ms >= 0
    assert report.stage_timings[0].stage == "collect"
    assert report.stage_timings[0].duration_ms >= 0
    assert report.results[0].stage_timings
    for timing in report.results[0].stage_timings:
        assert isinstance(timing, StageTiming)
        assert timing.duration_ms >= 0


@pytest.mark.asyncio
async def test_service_wrapper_delegates_to_orchestrator() -> None:
    orchestrator_mock = AsyncMock(spec=LeadGenerationOrchestrator)
    run_mock = AsyncMock(return_value=LeadGenerationReport())
    orchestrator_mock.run = run_mock
    service = LeadGenerationService(orchestrator=orchestrator_mock)
    await service.run(limit=3, persist=False, generate_emails=False, enqueue_emails=False)

    run_mock.assert_awaited_once_with(
        limit=3,
        persist=False,
        generate_emails=False,
        enqueue_emails=False,
    )


@pytest.mark.asyncio
async def test_collection_failure_returns_report() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(side_effect=RuntimeError("collect failed"))
    harness = build_orchestrator(collection_service=collection_service)
    report = await harness.orchestrator.run()

    assert report.success is False
    assert report.statistics.total_collected == 0
    assert report.statistics.processed == 0
    assert "collect failed" in report.errors[0]
    assert report.stage_timings[0].stage == "collect"
    assert report.stage_timings[0].success is False
