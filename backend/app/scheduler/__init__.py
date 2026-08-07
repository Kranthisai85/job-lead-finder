"""Scheduler and background job orchestration."""

from app.scheduler import jobs  # noqa: F401 — registers scheduled jobs
from app.scheduler.base import ScheduledJob
from app.scheduler.registry import ScheduledJobRegistry
from app.scheduler.scheduler import LeadScheduler
from app.scheduler.service import SchedulerService, get_scheduler_service
from app.scheduler.types import (
    JobExecutionMetrics,
    ScheduledJobResult,
    SchedulerState,
    SchedulerStatus,
)

__all__ = [
    "JobExecutionMetrics",
    "LeadScheduler",
    "ScheduledJob",
    "ScheduledJobRegistry",
    "ScheduledJobResult",
    "SchedulerService",
    "SchedulerState",
    "SchedulerStatus",
    "get_scheduler_service",
]
