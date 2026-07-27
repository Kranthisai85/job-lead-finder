from app.jobs.base import BaseJob
from app.jobs.registry import JobRegistry
from app.jobs.types import JobContext, JobResult


@JobRegistry.register("producthunt_collect")
class ProductHuntCollectJob(BaseJob):
    async def execute(self, context: JobContext) -> JobResult:
        _ = context
        return JobResult(success=True, processed=0, failed=0, errors=[])
