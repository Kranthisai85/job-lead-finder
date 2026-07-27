from collections.abc import Callable

from app.jobs.base import BaseJob


class JobRegistry:
    _jobs: dict[str, type[BaseJob]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[BaseJob]], type[BaseJob]]:
        def decorator(job_cls: type[BaseJob]) -> type[BaseJob]:
            cls._jobs[name.lower()] = job_cls
            return job_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseJob]:
        job_cls = cls._jobs.get(name.lower())
        if job_cls is None:
            raise KeyError(f"Job '{name}' is not registered")
        return job_cls

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._jobs.keys())
