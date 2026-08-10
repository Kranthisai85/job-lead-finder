from __future__ import annotations

from app.core.config import settings
from app.core.logger import get_logger
from app.lead_generation.service import LeadGenerationService
from app.pipeline.service import LeadPipelineService
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.types import ScheduledJobResult, SchedulerStatus
from app.source_manager.service import SourceCollectionService

_scheduler_service: SchedulerService | None = None


class SchedulerService:
    """Public entrypoint for the background job scheduler."""

    def __init__(
        self,
        *,
        scheduler: LeadScheduler | None = None,
        collection_service: SourceCollectionService | None = None,
        pipeline_service: LeadPipelineService | None = None,
        lead_generation_service: LeadGenerationService | None = None,
    ) -> None:
        self.logger = get_logger(__name__)
        self.scheduler = scheduler or LeadScheduler(
            collection_service=collection_service,
            pipeline_service=pipeline_service,
            lead_generation_service=lead_generation_service,
        )

    def start(self) -> None:
        self.logger.info(
            "[SCHEDULER] service=SchedulerService action=start enabled=%s",
            settings.scheduler_enabled,
        )
        self.scheduler.start()

    def reschedule(self, *, hour: int, minute: int) -> None:
        self.logger.info(
            "[SCHEDULER] service=SchedulerService action=reschedule schedule=%02d:%02d",
            hour,
            minute,
        )
        self.scheduler.reschedule(hour=hour, minute=minute)

    def shutdown(self, *, wait: bool = False) -> None:
        self.logger.info("[SCHEDULER] service=SchedulerService action=shutdown")
        self.scheduler.shutdown(wait=wait)

    async def run_job(self, job_name: str) -> ScheduledJobResult:
        self.logger.info("[SCHEDULER] service=SchedulerService action=run_job job=%s", job_name)
        return await self.scheduler.run_job(job_name)

    async def run_all_once(self) -> list[ScheduledJobResult]:
        self.logger.info("[SCHEDULER] service=SchedulerService action=run_all_once")
        return await self.scheduler.run_all_once()

    def status(self) -> SchedulerStatus:
        return self.scheduler.status()


def get_scheduler_service() -> SchedulerService:
    """Process-wide singleton — prevents duplicate scheduler instances."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


def reset_scheduler_service_for_tests() -> None:
    """Test helper to clear the process singleton."""
    global _scheduler_service
    if _scheduler_service is not None:
        try:
            _scheduler_service.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler_service = None
