from app.core.config import settings
from app.core.logger import get_logger
from app.pipeline.service import LeadPipelineService
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.types import ScheduledJobResult, SchedulerStatus
from app.source_manager.service import SourceCollectionService


class SchedulerService:
    """Public entrypoint for the background job scheduler."""

    def __init__(
        self,
        *,
        scheduler: LeadScheduler | None = None,
        collection_service: SourceCollectionService | None = None,
        pipeline_service: LeadPipelineService | None = None,
    ) -> None:
        self.logger = get_logger(__name__)
        self.scheduler = scheduler or LeadScheduler(
            collection_service=collection_service,
            pipeline_service=pipeline_service,
        )

    def start(self) -> None:
        self.logger.info(
            "service=SchedulerService action=start enabled=%s", settings.scheduler_enabled
        )
        self.scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        self.logger.info("service=SchedulerService action=shutdown")
        self.scheduler.shutdown(wait=wait)

    async def run_job(self, job_name: str) -> ScheduledJobResult:
        self.logger.info("service=SchedulerService action=run_job job=%s", job_name)
        return await self.scheduler.run_job(job_name)

    async def run_all_once(self) -> list[ScheduledJobResult]:
        self.logger.info("service=SchedulerService action=run_all_once")
        return await self.scheduler.run_all_once()

    def status(self) -> SchedulerStatus:
        return self.scheduler.status()
