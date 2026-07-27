from typing import Any

from app.jobs.base import BaseJob
from app.jobs.factory import JobFactory
from app.jobs.types import JobContext, JobResult


class JobRunner:
    async def run(self, job: BaseJob, context: JobContext) -> JobResult:
        return await job.run(context)

    async def run_job_type(
        self,
        job_type: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> JobResult:
        context = JobContext(job_type=job_type, metadata=metadata or {})
        job = JobFactory.create(job_type)
        return await self.run(job, context)
