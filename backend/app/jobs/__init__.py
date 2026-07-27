"""Job execution framework."""

from app.jobs import producthunt_collect  # noqa: F401 — registers jobs
from app.jobs.base import BaseJob
from app.jobs.factory import JobFactory
from app.jobs.registry import JobRegistry
from app.jobs.runner import JobRunner
from app.jobs.types import JobContext, JobResult

__all__ = [
    "BaseJob",
    "JobContext",
    "JobFactory",
    "JobRegistry",
    "JobResult",
    "JobRunner",
]
