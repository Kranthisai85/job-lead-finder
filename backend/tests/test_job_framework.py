import asyncio

import pytest

import app.jobs  # noqa: F401
from app.jobs.base import BaseJob
from app.jobs.factory import JobFactory
from app.jobs.registry import JobRegistry
from app.jobs.runner import JobRunner
from app.jobs.types import JobContext, JobResult


class SuccessJob(BaseJob):
    async def execute(self, context: JobContext) -> JobResult:
        _ = context
        return JobResult(success=True, processed=3, failed=0, errors=[])


class FailingJob(BaseJob):
    async def execute(self, context: JobContext) -> JobResult:
        _ = context
        raise RuntimeError("Job execution failed")


class SlowJob(BaseJob):
    async def execute(self, context: JobContext) -> JobResult:
        _ = context
        await asyncio.sleep(0.01)
        return JobResult(success=True, processed=1, failed=0, errors=[])


@JobRegistry.register("test-success")
class RegisteredSuccessJob(SuccessJob):
    pass


def test_job_registry_register_get_list() -> None:
    assert "producthunt_collect" in JobRegistry.list()
    assert "test-success" in JobRegistry.list()
    assert JobRegistry.get("producthunt_collect").__name__ == "ProductHuntCollectJob"


def test_job_registry_unknown_job() -> None:
    with pytest.raises(KeyError):
        JobRegistry.get("unknown-job")


def test_job_factory_create_producthunt_collect() -> None:
    job = JobFactory.create("producthunt_collect")
    assert job.__class__.__name__ == "ProductHuntCollectJob"


@pytest.mark.asyncio
async def test_base_job_successful_execution() -> None:
    job = SuccessJob()
    context = JobContext(job_type="test-success")

    result = await job.run(context)

    assert result.success is True
    assert result.processed == 3
    assert result.failed == 0
    assert result.duration_ms >= 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_base_job_error_handling() -> None:
    job = FailingJob()
    context = JobContext(job_type="failing")

    result = await job.run(context)

    assert result.success is False
    assert result.processed == 0
    assert result.failed == 1
    assert len(result.errors) == 1
    assert "Job execution failed" in result.errors[0]


@pytest.mark.asyncio
async def test_base_job_execution_timing() -> None:
    job = SlowJob()
    context = JobContext(job_type="slow")

    result = await job.run(context)

    assert result.success is True
    assert result.duration_ms >= 10


@pytest.mark.asyncio
async def test_job_runner_executes_job() -> None:
    runner = JobRunner()
    job = SuccessJob()
    context = JobContext(job_type="runner-test")

    result = await runner.run(job, context)

    assert result.success is True
    assert result.processed == 3


@pytest.mark.asyncio
async def test_job_runner_run_job_type() -> None:
    runner = JobRunner()

    result = await runner.run_job_type("producthunt_collect", metadata={"source": "test"})

    assert result.success is True
    assert result.processed == 0
