from typing import Any, AsyncIterator

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models import DOCUMENT_MODELS


@pytest.fixture()
async def test_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_test"]
    await init_beanie(database=database, document_models=DOCUMENT_MODELS)
    yield database
    for model in DOCUMENT_MODELS:
        await model.delete_all()
    client.close()
