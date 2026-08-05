from __future__ import annotations

from collections.abc import Callable

from app.scheduler.base import ScheduledJob


class ScheduledJobRegistry:
    _jobs: dict[str, type[ScheduledJob]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[ScheduledJob]], type[ScheduledJob]]:
        def decorator(job_cls: type[ScheduledJob]) -> type[ScheduledJob]:
            cls._jobs[name.lower()] = job_cls
            return job_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[ScheduledJob]:
        job_cls = cls._jobs.get(name.lower())
        if job_cls is None:
            raise KeyError(f"Scheduled job '{name}' is not registered")
        return job_cls

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._jobs.keys())

    @classmethod
    def create(cls, name: str) -> ScheduledJob:
        return cls.get(name)()
