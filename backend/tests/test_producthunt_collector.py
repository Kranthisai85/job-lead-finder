from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import app.collectors  # noqa: F401
from app.collectors.factory import CollectorFactory
from app.collectors.producthunt import ProductHuntCollector
from app.collectors.producthunt_parser import (
    extract_topics,
    parse_launch_date,
    parse_product_hunt_response,
)
from app.repositories.company_repository import CompanyRepository
from app.services.company_service import CompanyService

SAMPLE_PRODUCT = {
    "id": "123",
    "name": "Acme",
    "tagline": "Build faster",
    "slug": "acme",
    "url": "https://www.producthunt.com/posts/acme",
    "website": "https://www.acme.com/",
    "createdAt": "2024-01-15T10:00:00Z",
    "topics": {
        "edges": [
            {"node": {"name": "SaaS"}},
            {"node": {"name": "Developer Tools"}},
        ]
    },
}

SAMPLE_GRAPHQL_RESPONSE: dict[str, Any] = {
    "data": {
        "posts": {
            "edges": [{"node": SAMPLE_PRODUCT}],
        }
    }
}


def test_parse_product_hunt_response_success() -> None:
    products = parse_product_hunt_response(SAMPLE_GRAPHQL_RESPONSE)

    assert len(products) == 1
    assert products[0]["name"] == "Acme"
    assert products[0]["website"] == "https://www.acme.com/"


def test_parse_product_hunt_response_empty() -> None:
    assert parse_product_hunt_response({}) == []
    assert parse_product_hunt_response({"data": {"posts": {"edges": []}}}) == []


def test_parse_product_hunt_response_malformed() -> None:
    assert parse_product_hunt_response({"data": "invalid"}) == []
    assert parse_product_hunt_response({"data": {"posts": None}}) == []
    assert parse_product_hunt_response({"data": {"posts": {"edges": [None, "bad"]}}}) == []


def test_extract_topics() -> None:
    topics = extract_topics(SAMPLE_PRODUCT)
    assert topics == ["SaaS", "Developer Tools"]


def test_parse_launch_date() -> None:
    parsed = parse_launch_date("2024-01-15T10:00:00Z")
    assert parsed is not None
    assert parsed.year == 2024
    assert parse_launch_date("invalid-date") is None


@pytest.mark.asyncio
async def test_producthunt_normalize_maps_company_lead(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)

    leads = await collector.normalize([SAMPLE_PRODUCT])

    assert len(leads) == 1
    assert leads[0].name == "Acme"
    assert leads[0].website == "https://www.acme.com/"
    assert leads[0].description == "Build faster"
    assert leads[0].source == "producthunt"
    assert leads[0].tags == ["SaaS", "Developer Tools"]
    assert leads[0].metadata["product_hunt_url"] == "https://www.producthunt.com/posts/acme"
    assert leads[0].metadata["launch_date"] == "2024-01-15T10:00:00Z"


@pytest.mark.asyncio
async def test_producthunt_normalize_skips_missing_website(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)

    product_without_website = {**SAMPLE_PRODUCT, "website": ""}
    leads = await collector.normalize([product_without_website])

    assert leads == []


@pytest.mark.asyncio
async def test_producthunt_collector_run_success(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)

    duplicate_product = {
        **SAMPLE_PRODUCT,
        "id": "456",
        "name": "Acme Duplicate",
        "website": "http://www.acme.com",
    }

    with patch(
        "app.collectors.producthunt.fetch_latest_product_hunt_posts",
        new=AsyncMock(return_value=([SAMPLE_PRODUCT, duplicate_product], 1)),
    ):
        result = await collector.run()

    assert result.collector_name == "producthunt"
    assert result.collected_count == 2
    assert result.normalized_count == 2
    assert result.valid_count == 1
    assert result.saved_count == 1


@pytest.mark.asyncio
async def test_producthunt_collector_unavailable_returns_empty(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = CollectorFactory.create("producthunt", service)

    with patch(
        "app.collectors.producthunt.fetch_latest_product_hunt_posts",
        new=AsyncMock(return_value=([], 0)),
    ):
        result = await collector.run()

    assert result.collected_count == 0
    assert result.saved_count == 0


@pytest.mark.asyncio
async def test_producthunt_fetch_unavailable_returns_empty() -> None:
    from app.collectors.producthunt_parser import fetch_latest_product_hunt_posts

    class FailingClient:
        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise ConnectionError("Product Hunt unavailable")

        async def aclose(self) -> None:
            return None

    products, pages = await fetch_latest_product_hunt_posts(
        client=FailingClient(),  # type: ignore[arg-type]
    )

    assert products == []
    assert pages == 0
