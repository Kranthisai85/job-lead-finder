from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter

from app.core.config import settings
from app.core.logger import get_logger
from app.scheduler.types import ScheduledJobResult


class ScheduledJob(ABC):
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def cron_expression(self) -> str:
        raise NotImplementedError

    @property
    def enabled(self) -> bool:
        return settings.scheduler_enabled

    @property
    def timeout_seconds(self) -> float:
        return float(settings.max_job_runtime)

    @abstractmethod
    async def execute(self) -> ScheduledJobResult:
        raise NotImplementedError

    async def run(self) -> ScheduledJobResult:
        started_at = perf_counter()
        self.logger.info("scheduled_job=%s status=started", self.name)

        try:
            result = await self.execute()
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            final_result = result.model_copy(update={"duration_ms": duration_ms})
        except Exception as exc:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            self.logger.exception(
                "scheduled_job=%s status=failed error=%s duration_ms=%.2f",
                self.name,
                exc,
                duration_ms,
            )
            final_result = ScheduledJobResult(
                job_name=self.name,
                success=False,
                duration_ms=duration_ms,
                errors=[str(exc)],
            )

        status = "finished" if final_result.success else "failed"
        self.logger.info(
            "scheduled_job=%s status=%s duration_ms=%.2f processed=%d failed=%d",
            self.name,
            status,
            final_result.duration_ms,
            final_result.processed,
            final_result.failed,
        )
        return final_result
