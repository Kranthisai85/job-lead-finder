"""Manual Run Now API tests."""

from __future__ import annotations

from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.v1.jobs as jobs_api
from app.main import app
from app.scheduler.jobs import DAILY_LEAD_GENERATION_JOB
from app.scheduler.types import ScheduledJobResult


@pytest.fixture(autouse=True)
def reset_manual_run_flag() -> None:
    jobs_api._manual_run_active = False


@pytest.fixture()
async def api_client(test_db: Any) -> AsyncIterator[AsyncClient]:
    import app.db.mongo as mongo_module

    mongo_module.client = test_db.client

    with (
        patch.object(mongo_module, "connect_to_mongo", new=AsyncMock()),
        patch.object(mongo_module, "close_mongo_connection", new=AsyncMock()),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    mongo_module.client = None


@pytest.mark.asyncio
async def test_run_now_starts_job_in_background(api_client: AsyncClient) -> None:
    result = ScheduledJobResult(job_name=DAILY_LEAD_GENERATION_JOB, success=True, processed=2)
    with patch("app.api.v1.jobs.get_scheduler_service") as get_service:
        service = AsyncMock()
        service.run_job = AsyncMock(return_value=result)
        get_service.return_value = service

        response = await api_client.post("/api/v1/jobs/run-now")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["status"] == "started"
        assert payload["data"]["job_name"] == DAILY_LEAD_GENERATION_JOB

        import asyncio

        await asyncio.sleep(0.05)
        service.run_job.assert_awaited_with(DAILY_LEAD_GENERATION_JOB)


@pytest.mark.asyncio
async def test_run_now_rejects_concurrent_start(api_client: AsyncClient) -> None:
    jobs_api._manual_run_active = True
    response = await api_client.post("/api/v1/jobs/run-now")
    assert response.status_code == 409
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_run_now_status_idle(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/jobs/run-now/status")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "idle"
