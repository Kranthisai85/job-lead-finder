from abc import ABC, abstractmethod
from time import perf_counter

from app.core.logger import get_logger
from app.jobs.types import JobContext, JobResult


class BaseJob(ABC):
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    async def execute(self, context: JobContext) -> JobResult:
        raise NotImplementedError

    async def run(self, context: JobContext) -> JobResult:
        started_at = perf_counter()
        self.logger.info(
            "job_id=%s job_type=%s status=started",
            context.job_id,
            context.job_type,
        )

        try:
            result = await self.execute(context)
            duration_ms = (perf_counter() - started_at) * 1000
            final_result = result.model_copy(update={"duration_ms": duration_ms})
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            self.logger.exception(
                "job_id=%s job_type=%s status=failed error=%s",
                context.job_id,
                context.job_type,
                exc,
            )
            final_result = JobResult(
                success=False,
                processed=0,
                failed=1,
                duration_ms=duration_ms,
                errors=[str(exc)],
            )

        if final_result.errors:
            for error in final_result.errors:
                self.logger.error(
                    "job_id=%s job_type=%s error=%s",
                    context.job_id,
                    context.job_type,
                    error,
                )

        self.logger.info(
            (
                "job_id=%s job_type=%s success=%s processed=%d failed=%d "
                "duration_ms=%.2f status=finished"
            ),
            context.job_id,
            context.job_type,
            final_result.success,
            final_result.processed,
            final_result.failed,
            final_result.duration_ms,
        )
        return final_result
