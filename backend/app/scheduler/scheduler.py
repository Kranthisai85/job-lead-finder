from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logger import get_logger
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import StartupSeed
from app.scheduler.base import ScheduledJob
from app.scheduler.jobs import CleanupJob, CollectLeadsJob, ValidationJob
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.types import JobExecutionMetrics, ScheduledJobResult, SchedulerStatus
from app.source_manager.service import SourceCollectionService


class LeadScheduler:
    """APScheduler-backed orchestrator for registered scheduled jobs."""

    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler | None = None,
        collection_service: SourceCollectionService | None = None,
        pipeline_service: LeadPipelineService | None = None,
    ) -> None:
        self.scheduler = scheduler or AsyncIOScheduler(timezone="UTC")
        self.collection_service = collection_service or SourceCollectionService()
        self.pipeline_service = pipeline_service or LeadPipelineService()
        self.logger = get_logger(__name__)
        self._metrics: dict[str, JobExecutionMetrics] = {}
        self._last_collected_seeds: list[StartupSeed] = []
        self._running = False

    @property
    def last_collected_seeds(self) -> list[StartupSeed]:
        return list(self._last_collected_seeds)

    def start(self) -> None:
        if self._running:
            return
        if not settings.scheduler_enabled:
            self.logger.info("scheduler_disabled status=skipped")
            return

        for job_name in ScheduledJobRegistry.list():
            job = self._create_job(job_name)
            if not job.enabled:
                continue
            trigger = CronTrigger.from_crontab(job.cron_expression)
            self.scheduler.add_job(
                self._scheduled_wrapper(job),
                trigger=trigger,
                id=job.name,
                replace_existing=True,
                name=job.name,
            )
            self._ensure_metrics(job.name)

        self.scheduler.start()
        self._running = True
        self._refresh_next_executions()
        self.logger.info(
            "scheduler_started jobs=%s",
            ScheduledJobRegistry.list(),
        )

    def shutdown(self, *, wait: bool = False) -> None:
        if not self._running:
            return
        self.scheduler.shutdown(wait=wait)
        self._running = False
        self.logger.info("scheduler_stopped")

    async def run_job(self, job_name: str) -> ScheduledJobResult:
        job = self._create_job(job_name)
        return await self._execute_job(job)

    async def run_all_once(self) -> list[ScheduledJobResult]:
        results: list[ScheduledJobResult] = []
        for job_name in ScheduledJobRegistry.list():
            job = self._create_job(job_name)
            if job.enabled:
                results.append(await self._execute_job(job))
        return results

    def status(self) -> SchedulerStatus:
        self._refresh_next_executions()
        return SchedulerStatus(
            running=self._running,
            enabled=settings.scheduler_enabled,
            jobs=[self._metrics[name] for name in ScheduledJobRegistry.list()],
        )

    def _create_job(self, job_name: str) -> ScheduledJob:
        if job_name == "collect_leads":
            return CollectLeadsJob(
                collection_service=self.collection_service,
                on_collected=self._store_collected_seeds,
            )
        if job_name == "validation":
            return ValidationJob(
                pipeline_service=self.pipeline_service,
                seeds_provider=lambda: self.last_collected_seeds,
            )
        if job_name == "cleanup":
            return CleanupJob()
        return ScheduledJobRegistry.create(job_name)

    def _store_collected_seeds(self, seeds: list[StartupSeed]) -> None:
        self._last_collected_seeds = list(seeds)
        self.logger.info("scheduler_state collected_seeds=%d", len(seeds))

    def _scheduled_wrapper(self, job: ScheduledJob) -> Callable[[], Any]:
        async def _runner() -> None:
            await self._execute_job(job)

        return _runner

    async def _execute_job(self, job: ScheduledJob) -> ScheduledJobResult:
        started_at = datetime.now(timezone.utc)
        metrics = self._ensure_metrics(job.name)
        metrics.started_at = started_at
        metrics.error = None

        self.logger.info("scheduler_job_started job=%s", job.name)
        try:
            result = await asyncio.wait_for(job.run(), timeout=job.timeout_seconds)
        except TimeoutError:
            result = ScheduledJobResult(
                job_name=job.name,
                success=False,
                errors=[f"Job timed out after {job.timeout_seconds}s"],
            )
        except Exception as exc:
            result = ScheduledJobResult(
                job_name=job.name,
                success=False,
                errors=[str(exc)],
            )

        finished_at = datetime.now(timezone.utc)
        metrics.finished_at = finished_at
        metrics.duration_ms = result.duration_ms
        metrics.success = result.success
        metrics.error = result.errors[0] if result.errors else None
        metrics.last_execution = finished_at
        self._metrics[job.name] = metrics
        self._refresh_next_executions()

        if result.success:
            self.logger.info(
                "scheduler_job_finished job=%s duration_ms=%.2f processed=%d",
                job.name,
                result.duration_ms,
                result.processed,
            )
        else:
            self.logger.warning(
                "scheduler_job_failed job=%s duration_ms=%.2f errors=%s",
                job.name,
                result.duration_ms,
                result.errors,
            )
        return result

    def _ensure_metrics(self, job_name: str) -> JobExecutionMetrics:
        if job_name not in self._metrics:
            self._metrics[job_name] = JobExecutionMetrics(job_name=job_name)
        return self._metrics[job_name]

    def _refresh_next_executions(self) -> None:
        if not self._running:
            for job_name in ScheduledJobRegistry.list():
                metrics = self._ensure_metrics(job_name)
                metrics.next_execution = None
            return

        for scheduled_job in self.scheduler.get_jobs():
            metrics = self._ensure_metrics(str(scheduled_job.name))
            next_run = scheduled_job.next_run_time
            metrics.next_execution = (
                next_run.astimezone(timezone.utc) if next_run is not None else None
            )
