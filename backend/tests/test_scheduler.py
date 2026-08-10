from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger

import app.scheduler.jobs  # noqa: F401 — ensure jobs are registered
from app.collectors.types import CompanyLead
from app.core.config import settings
from app.lead_generation.types import LeadGenerationReport, LeadGenerationStatistics
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.scheduler.jobs import (
    DAILY_LEAD_GENERATION_JOB,
    CleanupJob,
    CollectLeadsJob,
    DailyLeadGenerationJob,
    ValidationJob,
)
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.service import (
    SchedulerService,
    get_scheduler_service,
    reset_scheduler_service_for_tests,
)
from app.scheduler.types import ScheduledJobResult
from app.source_manager.types import SourceCollectionReport


def make_seed(name: str = "Acme", website: str = "https://acme.example") -> StartupSeed:
    return StartupSeed(name=name, website=website, description="Desc", source="test")


def make_lead(success: bool = True) -> CompleteLead:
    return CompleteLead(
        startup=make_seed(),
        processing=ProcessingMetadata(success=success, errors=[] if success else ["failed"]),
    )


def make_collection_report(count: int = 2) -> SourceCollectionReport:
    return SourceCollectionReport(
        collectors_run=["stub"],
        total_found=count,
        unique_companies=[
            CompanyLead(
                name=f"Co {index}",
                website=f"https://co{index}.example",
                source="stub",
            )
            for index in range(count)
        ],
        execution_time_ms=12.0,
    )


def make_pipeline_report(*, success: bool = True) -> LeadGenerationReport:
    return LeadGenerationReport(
        success=success,
        statistics=LeadGenerationStatistics(
            total_collected=1,
            processed=1,
            persisted=1,
            qualified=1,
            emails_generated=1,
            queued=1,
            failed=0 if success else 1,
            duration_ms=12.5,
        ),
        errors=[] if success else ["boom"],
    )


def test_scheduled_job_registry_register_get_list() -> None:
    assert "collect_leads" in ScheduledJobRegistry.list()
    assert "validation" in ScheduledJobRegistry.list()
    assert "cleanup" in ScheduledJobRegistry.list()
    assert DAILY_LEAD_GENERATION_JOB in ScheduledJobRegistry.list()
    assert ScheduledJobRegistry.get("collect_leads").__name__ == "RegisteredCollectLeadsJob"

    with pytest.raises(KeyError):
        ScheduledJobRegistry.get("unknown-job")


@pytest.mark.asyncio
async def test_collect_leads_job_calls_collection_service() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(2))
    stored: list[StartupSeed] = []

    job = CollectLeadsJob(
        collection_service=collection_service,
        on_collected=lambda seeds: stored.extend(seeds),
    )
    result = await job.run()

    collection_service.collect_all.assert_awaited_once()
    assert result.success is True
    assert result.processed == 2
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_validation_job_runs_pipeline_over_seeds() -> None:
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(return_value=make_lead(success=True))

    job = ValidationJob(
        pipeline_service=pipeline_service,
        seeds_provider=lambda: [
            make_seed("A", "https://a.example"),
            make_seed("B", "https://b.example"),
        ],
    )
    result = await job.run()

    assert pipeline_service.process.await_count == 2
    assert result.processed == 2
    assert result.failed == 0


@pytest.mark.asyncio
async def test_validation_job_counts_failures() -> None:
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(
        side_effect=[make_lead(success=True), RuntimeError("boom")]
    )

    job = ValidationJob(
        pipeline_service=pipeline_service,
        seeds_provider=lambda: [
            make_seed("A", "https://a.example"),
            make_seed("B", "https://b.example"),
        ],
    )
    result = await job.run()

    assert result.processed == 1
    assert result.failed == 1
    assert result.success is False


@pytest.mark.asyncio
async def test_cleanup_job_logs_only() -> None:
    result = await CleanupJob().run()
    assert result.success is True
    assert result.details.get("action") == "log_only"


@pytest.mark.asyncio
async def test_manual_execution_via_service() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(1))
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(return_value=make_lead())

    scheduler = LeadScheduler(
        collection_service=collection_service,
        pipeline_service=pipeline_service,
    )
    service = SchedulerService(scheduler=scheduler)

    collect_result = await service.run_job("collect_leads")
    assert collect_result.success is True
    assert collect_result.processed == 1

    validation_result = await service.run_job("validation")
    assert validation_result.processed == 1
    pipeline_service.process.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_all_once() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(0))
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(return_value=make_lead())
    lead_generation_service = AsyncMock()
    lead_generation_service.run = AsyncMock(return_value=make_pipeline_report())

    service = SchedulerService(
        scheduler=LeadScheduler(
            collection_service=collection_service,
            pipeline_service=pipeline_service,
            lead_generation_service=lead_generation_service,
        )
    )

    results = await service.run_all_once()
    assert len(results) == 4
    assert {item.job_name for item in results} == {
        DAILY_LEAD_GENERATION_JOB,
        "collect_leads",
        "validation",
        "cleanup",
    }


@pytest.mark.asyncio
async def test_job_failure_does_not_stop_other_jobs() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(side_effect=RuntimeError("collect failed"))

    service = SchedulerService(scheduler=LeadScheduler(collection_service=collection_service))

    result = await service.run_job("collect_leads")
    cleanup_result = await service.run_job("cleanup")

    assert result.success is False
    assert cleanup_result.success is True


@pytest.mark.asyncio
async def test_status_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(1))

    scheduler = LeadScheduler(collection_service=collection_service)
    service = SchedulerService(scheduler=scheduler)

    await service.run_job("collect_leads")
    status = service.status()

    assert status.enabled is True
    assert len(status.jobs) >= 3
    collect_metrics = next(item for item in status.jobs if item.job_name == "collect_leads")
    assert collect_metrics.success is True
    assert collect_metrics.last_execution is not None
    assert collect_metrics.duration_ms >= 0


@pytest.mark.asyncio
async def test_scheduler_start_and_shutdown_with_mock_apscheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []

    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)
    service = SchedulerService(scheduler=lead_scheduler)

    with patch.object(lead_scheduler, "_create_job", wraps=lead_scheduler._create_job):
        service.start()

    mock_scheduler.start.assert_called_once()
    # Step 39: exactly one production daily job
    assert mock_scheduler.add_job.call_count == 1
    added = mock_scheduler.add_job.call_args
    assert added.kwargs["id"] == DAILY_LEAD_GENERATION_JOB
    trigger = added.kwargs["trigger"]
    assert isinstance(trigger, CronTrigger)

    status = service.status()
    assert status.running is True

    service.shutdown()
    mock_scheduler.shutdown.assert_called_once()
    assert service.status().running is False


@pytest.mark.asyncio
async def test_scheduled_execution_wrapper() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(1))
    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []

    lead_scheduler = LeadScheduler(
        scheduler=mock_scheduler,
        collection_service=collection_service,
    )

    job = lead_scheduler._create_job("collect_leads")
    runner = lead_scheduler._scheduled_wrapper(job)
    await runner()

    collection_service.collect_all.assert_awaited_once()
    collect_metrics = next(
        item for item in lead_scheduler.status().jobs if item.job_name == "collect_leads"
    )
    assert collect_metrics.success is True


@pytest.mark.asyncio
async def test_job_timeout() -> None:
    collection_service = AsyncMock()

    class SlowCollectJob(CollectLeadsJob):
        @property
        def timeout_seconds(self) -> float:
            return 0.01

        async def execute(self) -> ScheduledJobResult:
            import asyncio

            await asyncio.sleep(0.05)
            return ScheduledJobResult(job_name=self.name, success=True)

    lead_scheduler = LeadScheduler(collection_service=collection_service)
    result = await lead_scheduler._execute_job(SlowCollectJob())

    assert result.success is False
    assert "timed out" in result.errors[0].lower()


# --- Step 39 focused tests ---


def test_scheduler_disabled_does_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)
    service = SchedulerService(scheduler=lead_scheduler)

    service.start()

    mock_scheduler.start.assert_not_called()
    mock_scheduler.add_job.assert_not_called()
    assert service.status().running is False


def test_scheduler_enabled_registers_one_daily_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)
    SchedulerService(scheduler=lead_scheduler).start()

    assert mock_scheduler.add_job.call_count == 1
    assert mock_scheduler.add_job.call_args.kwargs["id"] == DAILY_LEAD_GENERATION_JOB


def test_scheduler_timezone_asia_kolkata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_timezone", "Asia/Kolkata")
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    LeadScheduler(scheduler=mock_scheduler).start()

    trigger = mock_scheduler.add_job.call_args.kwargs["trigger"]
    assert isinstance(trigger, CronTrigger)
    assert str(trigger.timezone) == "Asia/Kolkata"


def test_scheduler_time_is_09_00(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_hour", 9)
    monkeypatch.setattr(settings, "scheduler_minute", 0)
    monkeypatch.setattr(settings, "scheduler_timezone", "Asia/Kolkata")
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    LeadScheduler(scheduler=mock_scheduler).start()

    trigger = mock_scheduler.add_job.call_args.kwargs["trigger"]
    expected = CronTrigger(hour=9, minute=0, timezone=ZoneInfo("Asia/Kolkata"))
    assert isinstance(trigger, CronTrigger)
    assert str(trigger) == str(expected)


def test_scheduler_reschedule_updates_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_hour", 9)
    monkeypatch.setattr(settings, "scheduler_minute", 0)
    monkeypatch.setattr(settings, "scheduler_timezone", "Asia/Kolkata")
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    lead = LeadScheduler(scheduler=mock_scheduler)
    lead.start()
    mock_scheduler.running = True

    lead.reschedule(hour=15, minute=45)

    assert lead.schedule_hour == 15
    assert lead.schedule_minute == 45
    assert mock_scheduler.add_job.call_count == 2
    trigger = mock_scheduler.add_job.call_args.kwargs["trigger"]
    expected = CronTrigger(hour=15, minute=45, timezone=ZoneInfo("Asia/Kolkata"))
    assert str(trigger) == str(expected)


@pytest.mark.asyncio
async def test_scheduled_execution_calls_pipeline_once() -> None:
    lead_generation_service = AsyncMock()
    lead_generation_service.run = AsyncMock(return_value=make_pipeline_report())
    job = DailyLeadGenerationJob(lead_generation_service=lead_generation_service)

    result = await job.run()

    lead_generation_service.run.assert_awaited_once()
    assert "run_id" in lead_generation_service.run.await_args.kwargs
    assert result.success is True
    assert result.details["run_id"]


@pytest.mark.asyncio
async def test_pipeline_failure_does_not_kill_scheduler() -> None:
    lead_generation_service = AsyncMock()
    lead_generation_service.run = AsyncMock(side_effect=RuntimeError("pipeline down"))
    scheduler = LeadScheduler(lead_generation_service=lead_generation_service)

    first = await scheduler.run_job(DAILY_LEAD_GENERATION_JOB)
    assert first.success is False

    lead_generation_service.run = AsyncMock(return_value=make_pipeline_report())
    scheduler.lead_generation_service = lead_generation_service
    second = await scheduler.run_job(DAILY_LEAD_GENERATION_JOB)
    assert second.success is True


@pytest.mark.asyncio
async def test_scheduled_execution_never_sends_email() -> None:
    lead_generation_service = AsyncMock()
    lead_generation_service.run = AsyncMock(return_value=make_pipeline_report())
    send_pending = AsyncMock()
    send_one = AsyncMock()

    with (
        patch("app.email_queue.service.EmailQueueService.send_pending", send_pending),
        patch("app.email_queue.service.EmailQueueService.send_one", send_one),
    ):
        await DailyLeadGenerationJob(lead_generation_service=lead_generation_service).run()

    send_pending.assert_not_called()
    send_one.assert_not_called()
    lead_generation_service.run.assert_awaited_once()


def test_duplicate_initialization_does_not_add_duplicate_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)

    lead_scheduler.start()
    mock_scheduler.running = True
    lead_scheduler.start()

    assert mock_scheduler.add_job.call_count == 1
    assert mock_scheduler.start.call_count == 1


def test_scheduler_shutdown_releases_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    mock_scheduler = MagicMock()
    mock_scheduler.running = False
    mock_scheduler.get_jobs.return_value = []
    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)
    service = SchedulerService(scheduler=lead_scheduler)
    service.start()
    mock_scheduler.running = True
    service.shutdown(wait=False)
    mock_scheduler.shutdown.assert_called_once()
    assert service.status().running is False


@pytest.mark.asyncio
async def test_run_id_is_unique_per_scheduled_execution() -> None:
    lead_generation_service = AsyncMock()
    lead_generation_service.run = AsyncMock(return_value=make_pipeline_report())
    job = DailyLeadGenerationJob(lead_generation_service=lead_generation_service)

    first = await job.run()
    second = await job.run()

    run_ids = [call.kwargs["run_id"] for call in lead_generation_service.run.await_args_list]
    assert first.details["run_id"] != second.details["run_id"]
    assert run_ids[0] != run_ids[1]


def test_get_scheduler_service_is_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_scheduler_service_for_tests()
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    first = get_scheduler_service()
    second = get_scheduler_service()
    assert first is second
    reset_scheduler_service_for_tests()


def test_cron_trigger_zoneinfo_matches_config() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    trigger = CronTrigger(hour=9, minute=0, timezone=tz)
    assert str(trigger.timezone) == "Asia/Kolkata"
