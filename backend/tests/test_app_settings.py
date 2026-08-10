"""App settings + duplicate-company skip tests."""

from __future__ import annotations

from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.app_settings.service import AppSettingsService
from app.app_settings.types import AppSettingsUpdate
from app.email_queue.document import EmailQueueEntry
from app.email_queue.repository import QueueRepository
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueStatus
from app.models.app_settings import AppSettingsDocument
from app.models.company import Company
from tests.test_lead_generation import build_orchestrator


@pytest.fixture()
async def settings_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_settings_test"]
    await init_beanie(
        database=database,
        document_models=[AppSettingsDocument, EmailQueueEntry, Company],
    )
    yield database
    await AppSettingsDocument.delete_all()
    await EmailQueueEntry.delete_all()
    await Company.delete_all()
    client.close()


@pytest.mark.asyncio
async def test_app_settings_default_and_update(settings_db: Any) -> None:
    service = AppSettingsService()
    defaults = await service.get_settings()
    assert defaults.skip_duplicate_companies is True

    saved = await service.update_settings(AppSettingsUpdate(skip_duplicate_companies=False))
    assert saved.skip_duplicate_companies is False
    loaded = await service.get_settings()
    assert loaded.skip_duplicate_companies is False


@pytest.mark.asyncio
async def test_duplicate_company_detected_when_pending(settings_db: Any) -> None:
    await AppSettingsService().update_settings(AppSettingsUpdate(skip_duplicate_companies=True))
    await QueueRepository().create(
        {
            "company_id": "company1.example",
            "contact_id": "a@company1.example",
            "recipient_name": "Ada",
            "recipient_email": "a@company1.example",
            "subject": "Hi",
            "body": "Body",
            "status": EmailQueueStatus.PENDING,
        }
    )
    service = EmailQueueService()
    assert await service.is_duplicate_company(website="https://company1.example") is True
    assert await service.is_duplicate_company(website="https://other.example") is False


@pytest.mark.asyncio
async def test_duplicate_skip_disabled_allows_requeue(settings_db: Any) -> None:
    await AppSettingsService().update_settings(AppSettingsUpdate(skip_duplicate_companies=False))
    await QueueRepository().create(
        {
            "company_id": "company1.example",
            "contact_id": "a@company1.example",
            "recipient_name": "Ada",
            "recipient_email": "a@company1.example",
            "subject": "Hi",
            "body": "Body",
            "status": EmailQueueStatus.SKIPPED,
        }
    )
    service = EmailQueueService()
    assert await service.is_duplicate_company(website="https://company1.example") is False


@pytest.mark.asyncio
async def test_orchestrator_skips_duplicate_company_before_pipeline() -> None:
    harness = build_orchestrator()
    harness.orchestrator.email_queue_service.is_duplicate_company = AsyncMock(return_value=True)

    report = await harness.orchestrator.run(limit=1)

    assert report.statistics.queued == 0
    assert report.results[0].queued is False
    assert any("already in email queue" in warning for warning in report.results[0].warnings)
    harness.persist_mock.assert_not_called()
    harness.ai_generate_mock.assert_not_called()
    harness.enqueue_mock.assert_not_called()
