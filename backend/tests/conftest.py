from typing import Any, AsyncIterator

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.core.config import settings
from app.db.document_models import DOCUMENT_MODELS
from app.scheduler.service import reset_scheduler_service_for_tests


@pytest.fixture(autouse=True)
def _disable_scheduler_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep API/unit tests free of a live APScheduler unless a test re-enables it."""
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    reset_scheduler_service_for_tests()
    yield
    reset_scheduler_service_for_tests()


@pytest.fixture()
async def test_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_test"]
    await init_beanie(database=database, document_models=DOCUMENT_MODELS)
    yield database
    for model in DOCUMENT_MODELS:
        await model.delete_all()
    client.close()
