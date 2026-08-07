from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.core.config import settings
from app.core.logger import get_logger
from app.lead_generation.service import LeadGenerationService
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import StartupSeed
from app.scheduler.base import ScheduledJob
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.types import ScheduledJobResult
from app.source_manager.service import SourceCollectionService

logger = get_logger(__name__)

SeedCallback = Callable[[list[StartupSeed]], None]

DAILY_LEAD_GENERATION_JOB = "daily_lead_generation"


class DailyLeadGenerationJob(ScheduledJob):
    """Runs the full LeadGenerationService pipeline once per day. Never sends email."""

    def __init__(
        self,
        *,
        lead_generation_service: LeadGenerationService | None = None,
    ) -> None:
        super().__init__()
        self.lead_generation_service = lead_generation_service or LeadGenerationService()

    @property
    def name(self) -> str:
        return DAILY_LEAD_GENERATION_JOB

    @property
    def cron_expression(self) -> str:
        # Informational only — LeadScheduler builds a timezone-aware CronTrigger.
        return f"{settings.scheduler_minute} {settings.scheduler_hour} * * *"

    async def execute(self) -> ScheduledJobResult:
        run_id = str(uuid4())
        self.logger.info(
            "[SCHEDULER] Starting scheduled pipeline run_id=%s timezone=%s",
            run_id,
            settings.scheduler_timezone,
        )
        try:
            report = await self.lead_generation_service.run(run_id=run_id)
        except Exception as exc:
            self.logger.error(
                "[SCHEDULER] Pipeline failed run_id=%s error=%s",
                run_id,
                exc,
            )
            raise

        self.logger.info(
            "[SCHEDULER] Pipeline completed run_id=%s duration_ms=%.2f status=%s " "queued=%d",
            run_id,
            report.statistics.duration_ms,
            "success" if report.success else "failed",
            report.statistics.queued,
        )
        return ScheduledJobResult(
            job_name=self.name,
            success=report.success,
            processed=report.statistics.processed,
            failed=report.statistics.failed,
            errors=list(report.errors),
            details={
                "run_id": run_id,
                "queued": report.statistics.queued,
                "qualified": report.statistics.qualified,
                "emails_generated": report.statistics.emails_generated,
            },
        )


class CollectLeadsJob(ScheduledJob):
    def __init__(
        self,
        *,
        collection_service: SourceCollectionService | None = None,
        on_collected: SeedCallback | None = None,
    ) -> None:
        super().__init__()
        self.collection_service = collection_service or SourceCollectionService()
        self.on_collected = on_collected

    @property
    def name(self) -> str:
        return "collect_leads"

    @property
    def cron_expression(self) -> str:
        return settings.collect_cron

    async def execute(self) -> ScheduledJobResult:
        report = await self.collection_service.collect_all()
        seeds = [
            StartupSeed(
                name=lead.name,
                website=lead.website,
                description=lead.description,
                source=lead.source,
            )
            for lead in report.unique_companies
        ]
        if self.on_collected is not None:
            self.on_collected(seeds)

        return ScheduledJobResult(
            job_name=self.name,
            success=True,
            processed=len(seeds),
            failed=0,
            details={
                "total_found": report.total_found,
                "duplicates_removed": report.duplicates_removed,
                "collectors_run": report.collectors_run,
            },
        )


class ValidationJob(ScheduledJob):
    def __init__(
        self,
        *,
        pipeline_service: LeadPipelineService | None = None,
        seeds_provider: Callable[[], list[StartupSeed]] | None = None,
    ) -> None:
        super().__init__()
        self.pipeline_service = pipeline_service or LeadPipelineService()
        self.seeds_provider = seeds_provider or (lambda: [])

    @property
    def name(self) -> str:
        return "validation"

    @property
    def cron_expression(self) -> str:
        return settings.validation_cron

    async def execute(self) -> ScheduledJobResult:
        seeds = self.seeds_provider()
        processed = 0
        failed = 0
        errors: list[str] = []

        for seed in seeds:
            try:
                lead = await self.pipeline_service.process(seed)
                processed += 1
                if not lead.processing.success:
                    failed += 1
                    errors.extend(lead.processing.errors)
            except Exception as exc:
                failed += 1
                errors.append(f"{seed.name}: {exc}")

        return ScheduledJobResult(
            job_name=self.name,
            success=failed == 0,
            processed=processed,
            failed=failed,
            errors=errors,
            details={"companies_processed": processed},
        )


class CleanupJob(ScheduledJob):
    @property
    def name(self) -> str:
        return "cleanup"

    @property
    def cron_expression(self) -> str:
        return settings.cleanup_cron

    async def execute(self) -> ScheduledJobResult:
        logger.info("scheduled_job=cleanup action=log_only status=completed")
        return ScheduledJobResult(
            job_name=self.name,
            success=True,
            processed=0,
            failed=0,
            details={"action": "log_only"},
        )


@ScheduledJobRegistry.register(DAILY_LEAD_GENERATION_JOB)
class RegisteredDailyLeadGenerationJob(DailyLeadGenerationJob):
    pass


@ScheduledJobRegistry.register("collect_leads")
class RegisteredCollectLeadsJob(CollectLeadsJob):
    pass


@ScheduledJobRegistry.register("validation")
class RegisteredValidationJob(ValidationJob):
    pass


@ScheduledJobRegistry.register("cleanup")
class RegisteredCleanupJob(CleanupJob):
    pass
