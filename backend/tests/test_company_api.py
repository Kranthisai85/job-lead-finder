from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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
async def test_company_api_crud_flow(api_client: AsyncClient) -> None:
    create_response = await api_client.post(
        "/api/v1/companies",
        json={
            "name": "Acme",
            "website": "https://www.acme.com/",
            "description": "A company",
            "industry": "SaaS",
            "source": "manual",
        },
    )
    assert create_response.status_code == 201
    create_body = create_response.json()
    assert create_body["success"] is True
    assert create_body["data"]["website"] == "acme.com"
    company_id = create_body["data"]["id"]

    list_response = await api_client.get("/api/v1/companies?search=acme")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["data"]["total"] == 1

    get_response = await api_client.get(f"/api/v1/companies/{company_id}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["name"] == "Acme"

    patch_response = await api_client.patch(
        f"/api/v1/companies/{company_id}",
        json={"name": "Acme Updated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["name"] == "Acme Updated"

    delete_response = await api_client.delete(f"/api/v1/companies/{company_id}")
    assert delete_response.status_code == 200

    missing_response = await api_client.get(f"/api/v1/companies/{company_id}")
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_company_api_duplicate_website(api_client: AsyncClient) -> None:
    payload = {"name": "One", "website": "https://dup.example"}
    first_response = await api_client.post("/api/v1/companies", json=payload)
    assert first_response.status_code == 201

    second_response = await api_client.post(
        "/api/v1/companies",
        json={"name": "Two", "website": "http://dup.example"},
    )
    assert second_response.status_code == 409
    assert second_response.json()["success"] is False
