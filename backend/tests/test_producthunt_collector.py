from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.collectors  # noqa: F401
from app.collectors.factory import CollectorFactory
from app.collectors.producthunt import ProductHuntCollector
from app.collectors.producthunt_parser import (
    extract_topics,
    parse_launch_date,
    parse_product_hunt_response,
)
from app.collectors.producthunt_redirect import (
    extract_website_from_product_page,
    is_external_company_url,
    is_producthunt_redirect,
    resolve_company_website,
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


def test_is_producthunt_redirect() -> None:
    assert is_producthunt_redirect("https://www.producthunt.com/r/YVXYQHUZQFWTKE")
    assert is_producthunt_redirect("https://producthunt.com/r/abc")
    assert not is_producthunt_redirect("https://www.acme.com/")
    assert not is_producthunt_redirect("https://www.producthunt.com/posts/acme")
    assert not is_producthunt_redirect("")


def test_is_external_company_url() -> None:
    assert is_external_company_url("https://www.acme.com/")
    assert not is_external_company_url("https://www.producthunt.com/r/abc")
    assert not is_external_company_url("https://twitter.com/acme")
    assert not is_external_company_url("/relative")


def _mock_locator(*, href: str | None = None, count: int = 1) -> MagicMock:
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    locator.get_attribute = AsyncMock(return_value=href)
    locator.first = locator
    return locator


@pytest.mark.asyncio
async def test_extract_website_from_product_page_success() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.url = "https://www.producthunt.com/posts/acme"
    page.locator = MagicMock(
        side_effect=lambda selector: (
            _mock_locator(href="https://www.acme.com/")
            if selector == 'a[data-test="post-product-link"]'
            else _mock_locator(count=0)
        )
    )

    website = await extract_website_from_product_page(
        "https://www.producthunt.com/posts/acme",
        page=page,
        fallback_website="https://www.producthunt.com/r/YVXYQHUZQFWTKE",
    )

    assert website == "https://www.acme.com/"
    page.goto.assert_awaited()


@pytest.mark.asyncio
async def test_extract_website_follows_visit_redirect_with_playwright() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.url = "https://resolved.acme.com/"

    def locator_side_effect(selector: str) -> MagicMock:
        if selector == 'a[data-test="post-product-link"]':
            return _mock_locator(href="https://www.producthunt.com/r/YVXYQHUZQFWTKE")
        if selector == "a[href]":
            anchors = MagicMock()
            anchors.count = AsyncMock(return_value=0)
            return anchors
        return _mock_locator(count=0)

    page.locator = MagicMock(side_effect=locator_side_effect)
    page.get_by_role = MagicMock(return_value=_mock_locator(count=0))

    website = await extract_website_from_product_page(
        "https://www.producthunt.com/posts/acme",
        page=page,
        fallback_website="https://www.producthunt.com/r/YVXYQHUZQFWTKE",
    )

    assert website == "https://resolved.acme.com/"
    assert page.goto.await_count == 2


@pytest.mark.asyncio
async def test_resolve_company_website_skips_non_redirect() -> None:
    page = MagicMock()
    page.goto = AsyncMock()

    final = await resolve_company_website(
        "https://www.acme.com/",
        product_page_url="https://www.producthunt.com/posts/acme",
        page=page,
    )

    assert final == "https://www.acme.com/"
    page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_company_website_fallback_without_product_url() -> None:
    original = "https://www.producthunt.com/r/YVXYQHUZQFWTKE"
    final = await resolve_company_website(original, product_page_url=None, page=MagicMock())
    assert final == original


@pytest.mark.asyncio
async def test_extract_website_failure_returns_fallback() -> None:
    page = MagicMock()
    page.goto = AsyncMock(side_effect=RuntimeError("navigation failed"))
    fallback = "https://www.producthunt.com/r/YVXYQHUZQFWTKE"

    website = await extract_website_from_product_page(
        "https://www.producthunt.com/posts/acme",
        page=page,
        fallback_website=fallback,
    )

    assert website == fallback


@pytest.mark.asyncio
async def test_producthunt_normalize_resolves_redirect_urls(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)

    redirect_product = {
        **SAMPLE_PRODUCT,
        "website": "https://www.producthunt.com/r/YVXYQHUZQFWTKE",
    }

    with (
        patch(
            "app.collectors.producthunt.raw_items_need_website_resolution",
            return_value=True,
        ),
        patch(
            "app.collectors.producthunt.producthunt_browser_page",
        ) as browser_ctx,
        patch(
            "app.collectors.producthunt.resolve_company_website",
            new=AsyncMock(return_value="https://www.acme.com/"),
        ) as resolve_mock,
    ):
        page = MagicMock()
        browser_ctx.return_value.__aenter__ = AsyncMock(return_value=page)
        browser_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

        leads = await collector.normalize([redirect_product])

    assert len(leads) == 1
    assert leads[0].website == "https://www.acme.com/"
    assert leads[0].metadata["product_hunt_url"] == "https://www.producthunt.com/posts/acme"
    assert leads[0].metadata["website_redirect"] == "https://www.producthunt.com/r/YVXYQHUZQFWTKE"
    resolve_mock.assert_awaited_once()
    assert resolve_mock.await_args is not None
    assert resolve_mock.await_args.kwargs["product_page_url"] == (
        "https://www.producthunt.com/posts/acme"
    )
