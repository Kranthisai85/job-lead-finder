from app.jobs.base import BaseJob
from app.jobs.registry import JobRegistry


class JobFactory:
    @staticmethod
    def create(job_type: str) -> BaseJob:
        job_cls = JobRegistry.get(job_type)
        return job_cls()
