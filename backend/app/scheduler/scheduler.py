from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logger import get_logger
from app.lead_generation.service import LeadGenerationService
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import StartupSeed
from app.scheduler.base import ScheduledJob
from app.scheduler.jobs import (
    DAILY_LEAD_GENERATION_JOB,
    CleanupJob,
    CollectLeadsJob,
    DailyLeadGenerationJob,
    ValidationJob,
)
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.types import JobExecutionMetrics, ScheduledJobResult, SchedulerStatus
from app.source_manager.service import SourceCollectionService
from app.core.timezone import now_app


class LeadScheduler:
    """APScheduler-backed orchestrator for registered scheduled jobs."""

    # Production schedule: one daily full-pipeline job (Step 39).
    PRODUCTION_JOB_NAMES: tuple[str, ...] = (DAILY_LEAD_GENERATION_JOB,)

    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler | None = None,
        collection_service: SourceCollectionService | None = None,
        pipeline_service: LeadPipelineService | None = None,
        lead_generation_service: LeadGenerationService | None = None,
    ) -> None:
        self._timezone = ZoneInfo(settings.scheduler_timezone)
        self.scheduler = scheduler or AsyncIOScheduler(timezone=self._timezone)
        self.collection_service = collection_service or SourceCollectionService()
        self.pipeline_service = pipeline_service or LeadPipelineService()
        self.lead_generation_service = lead_generation_service or LeadGenerationService()
        self.logger = get_logger(__name__)
        self._metrics: dict[str, JobExecutionMetrics] = {}
        self._last_collected_seeds: list[StartupSeed] = []
        self._running = False
        self._hour = settings.scheduler_hour
        self._minute = settings.scheduler_minute

    @property
    def last_collected_seeds(self) -> list[StartupSeed]:
        return list(self._last_collected_seeds)

    @property
    def schedule_hour(self) -> int:
        return self._hour

    @property
    def schedule_minute(self) -> int:
        return self._minute

    def start(self) -> None:
        if self._running:
            self.logger.info("[SCHEDULER] already_running status=skipped")
            return
        if not settings.scheduler_enabled:
            self.logger.info("[SCHEDULER] Scheduler disabled status=skipped")
            return

        self._register_production_jobs()
        if not self.scheduler.running:
            self.scheduler.start()
        self._running = True
        self._refresh_next_executions()
        self._log_schedule_state(action="started")

    def reschedule(self, *, hour: int, minute: int) -> None:
        """Update daily cron time (live if scheduler already running)."""
        self._hour = int(hour)
        self._minute = int(minute)
        if not settings.scheduler_enabled:
            self.logger.info(
                "[SCHEDULER] reschedule_saved schedule=%02d:%02d enabled=false",
                self._hour,
                self._minute,
            )
            return
        if not self._running:
            self.logger.info(
                "[SCHEDULER] reschedule_saved schedule=%02d:%02d running=false",
                self._hour,
                self._minute,
            )
            return
        self._register_production_jobs()
        self._refresh_next_executions()
        self._log_schedule_state(action="rescheduled")

    def _register_production_jobs(self) -> None:
        for job_name in self.PRODUCTION_JOB_NAMES:
            job = self._create_job(job_name)
            if not job.enabled:
                continue
            trigger = CronTrigger(
                hour=self._hour,
                minute=self._minute,
                timezone=self._timezone,
            )
            self.scheduler.add_job(
                self._scheduled_wrapper(job),
                trigger=trigger,
                id=job.name,
                replace_existing=True,
                name=job.name,
                max_instances=1,
                coalesce=True,
            )
            self._ensure_metrics(job.name)

    def _log_schedule_state(self, *, action: str) -> None:
        next_runs = []
        for scheduled_job in self.scheduler.get_jobs():
            next_runs.append(f"{scheduled_job.id}={scheduled_job.next_run_time}")
        self.logger.info("[SCHEDULER] Scheduler %s", action)
        self.logger.info("[SCHEDULER] timezone=%s", settings.scheduler_timezone)
        self.logger.info(
            "[SCHEDULER] schedule=%02d:%02d jobs=%s",
            self._hour,
            self._minute,
            list(self.PRODUCTION_JOB_NAMES),
        )
        self.logger.info("[SCHEDULER] next_run=%s", "; ".join(next_runs) or "none")

    def shutdown(self, *, wait: bool = False) -> None:
        if not self._running:
            return
        try:
            self.scheduler.shutdown(wait=wait)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("[SCHEDULER] shutdown_error error=%s", exc)
        self._running = False
        self.logger.info("[SCHEDULER] Scheduler stopped")

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
        job_names = list(self.PRODUCTION_JOB_NAMES) + [
            name for name in ScheduledJobRegistry.list() if name not in self.PRODUCTION_JOB_NAMES
        ]
        return SchedulerStatus(
            running=self._running,
            enabled=settings.scheduler_enabled,
            jobs=[self._ensure_metrics(name) for name in job_names],
        )

    def _create_job(self, job_name: str) -> ScheduledJob:
        if job_name == DAILY_LEAD_GENERATION_JOB:
            return DailyLeadGenerationJob(
                lead_generation_service=self.lead_generation_service,
            )
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
        started_at = now_app()
        metrics = self._ensure_metrics(job.name)
        metrics.started_at = started_at
        metrics.error = None

        self.logger.info("[SCHEDULER] job_started job=%s", job.name)
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

        finished_at = now_app()
        metrics.finished_at = finished_at
        metrics.duration_ms = result.duration_ms
        metrics.success = result.success
        metrics.error = result.errors[0] if result.errors else None
        metrics.last_execution = finished_at
        self._metrics[job.name] = metrics
        self._refresh_next_executions()

        if result.success:
            self.logger.info(
                "[SCHEDULER] job_finished job=%s duration_ms=%.2f processed=%d",
                job.name,
                result.duration_ms,
                result.processed,
            )
        else:
            self.logger.warning(
                "[SCHEDULER] job_failed job=%s duration_ms=%.2f errors=%s",
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
            for job_name in self.PRODUCTION_JOB_NAMES:
                metrics = self._ensure_metrics(job_name)
                metrics.next_execution = None
            return

        for scheduled_job in self.scheduler.get_jobs():
            metrics = self._ensure_metrics(str(scheduled_job.id or scheduled_job.name))
            next_run = scheduled_job.next_run_time
            metrics.next_execution = (
                next_run.astimezone(timezone.utc) if next_run is not None else None
            )
