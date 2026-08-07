from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.types import GeneratedEmail
from app.email_queue.service import EmailQueueService
from app.main import app
from app.models.company import Company
from app.repositories.company_repository import CompanyRepository


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


async def _seed_pending_with_company() -> str:
    company = await CompanyRepository().create(
        Company(
            name="Acme Labs",
            website="acme.example",
            description="SaaS product",
            source="test",
            qualification_score=72,
            qualification_status="MEDIUM",
            qualification_reasons=[
                "No mobile app detected (+25)",
                "Product/software/startup company (+20)",
            ],
        )
    )
    item = await EmailQueueService().enqueue(
        generated_email=GeneratedEmail(
            subject="Hello Acme",
            opening="Hi there,",
            body="We noticed your product.",
            cta="Open to a quick call?",
            generation_source="fallback",
        ),
        company_id=str(company.id),
        contact_id="ada@acme.example",
        recipient_name="Ada Lovelace",
        recipient_email="ada@acme.example",
        lead_score=72.0,
    )
    return item.id


@pytest.mark.asyncio
async def test_list_pending_includes_company_qualification(api_client: AsyncClient) -> None:
    item_id = await _seed_pending_with_company()

    response = await api_client.get("/api/v1/email-queue/pending")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["id"] == item_id
    assert item["company_name"] == "Acme Labs"
    assert item["company_website"] == "acme.example"
    assert item["contact_name"] == "Ada Lovelace"
    assert item["contact_email"] == "ada@acme.example"
    assert item["qualification_score"] == 72
    assert item["qualification_status"] == "MEDIUM"
    assert "No mobile app detected (+25)" in item["qualification_reasons"]
    assert item["subject"] == "Hello Acme"
    assert "We noticed your product" in item["body"]
    assert item["status"] == "PENDING"


@pytest.mark.asyncio
async def test_approve_transitions_pending_to_approved(api_client: AsyncClient) -> None:
    item_id = await _seed_pending_with_company()

    response = await api_client.post(f"/api/v1/email-queue/{item_id}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "APPROVED"
    assert body["data"]["approved_at"] is not None

    pending = await api_client.get("/api/v1/email-queue/pending")
    assert pending.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_skip_transitions_pending_to_skipped(api_client: AsyncClient) -> None:
    item_id = await _seed_pending_with_company()

    response = await api_client.post(f"/api/v1/email-queue/{item_id}/skip")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "SKIPPED"

    pending = await api_client.get("/api/v1/email-queue/pending")
    assert pending.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_approve_non_pending_returns_404(api_client: AsyncClient) -> None:
    item_id = await _seed_pending_with_company()
    await api_client.post(f"/api/v1/email-queue/{item_id}/approve")

    response = await api_client.post(f"/api/v1/email-queue/{item_id}/approve")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sender_does_not_process_pending(api_client: AsyncClient) -> None:
    await _seed_pending_with_company()
    service = EmailQueueService()
    result = await service.send_pending()
    assert result.sent == 0
    stats = await service.statistics()
    assert stats.pending == 1
    assert stats.sent == 0
