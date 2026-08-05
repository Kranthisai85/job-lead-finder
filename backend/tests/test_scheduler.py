from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.scheduler.jobs  # noqa: F401 — ensure jobs are registered
from app.collectors.types import CompanyLead
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.scheduler.jobs import CleanupJob, CollectLeadsJob, ValidationJob
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.service import SchedulerService
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


def test_scheduled_job_registry_register_get_list() -> None:
    assert "collect_leads" in ScheduledJobRegistry.list()
    assert "validation" in ScheduledJobRegistry.list()
    assert "cleanup" in ScheduledJobRegistry.list()
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

    service = SchedulerService(
        scheduler=LeadScheduler(
            collection_service=collection_service,
            pipeline_service=pipeline_service,
        )
    )

    results = await service.run_all_once()
    assert len(results) == 3
    assert {item.job_name for item in results} == {"collect_leads", "validation", "cleanup"}


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
async def test_status_and_metrics() -> None:
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(return_value=make_collection_report(1))

    scheduler = LeadScheduler(collection_service=collection_service)
    service = SchedulerService(scheduler=scheduler)

    await service.run_job("collect_leads")
    status = service.status()

    assert status.enabled is True
    assert len(status.jobs) == 3
    collect_metrics = next(item for item in status.jobs if item.job_name == "collect_leads")
    assert collect_metrics.success is True
    assert collect_metrics.last_execution is not None
    assert collect_metrics.duration_ms >= 0


@pytest.mark.asyncio
async def test_scheduler_start_and_shutdown_with_mock_apscheduler() -> None:
    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []

    lead_scheduler = LeadScheduler(scheduler=mock_scheduler)
    service = SchedulerService(scheduler=lead_scheduler)

    with patch.object(lead_scheduler, "_create_job", wraps=lead_scheduler._create_job):
        service.start()

    mock_scheduler.start.assert_called_once()
    assert mock_scheduler.add_job.call_count == 3

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
