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
    WebsiteResolution,
    extract_via_external_links,
    extract_via_json_ld,
    extract_via_meta_tags,
    extract_via_next_data,
    extract_via_visit_button,
    is_external_company_url,
    is_intermediate_host,
    is_producthunt_redirect,
    page_has_cloudflare_challenge,
    resolve_company_website,
    strip_tracking_params,
)
from app.repositories.company_repository import CompanyRepository
from app.services.company_service import CompanyService
from app.utils.url import canonical_lead_website, website_identity

SAMPLE_PRODUCT = {
    "id": "123",
    "name": "Acme",
    "tagline": "Build faster",
    "slug": "acme",
    "url": "https://www.producthunt.com/products/acme",
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
    assert extract_topics(SAMPLE_PRODUCT) == ["SaaS", "Developer Tools"]


def test_parse_launch_date() -> None:
    parsed = parse_launch_date("2024-01-15T10:00:00Z")
    assert parsed is not None
    assert parsed.year == 2024
    assert parse_launch_date("invalid-date") is None


def test_website_identity_keeps_producthunt_redirects_unique() -> None:
    assert website_identity("https://www.producthunt.com/r/AAA") == "producthunt.com/r/aaa"
    assert website_identity("https://www.producthunt.com/r/BBB") == "producthunt.com/r/bbb"
    assert website_identity("https://www.acme.com/") == "acme.com"


def test_canonical_lead_website_preserves_redirect_path() -> None:
    assert (
        canonical_lead_website("https://www.producthunt.com/r/ABC?utm_source=x")
        == "https://www.producthunt.com/r/ABC"
    )
    assert canonical_lead_website("https://www.acme.com/") == "acme.com"


@pytest.mark.asyncio
async def test_producthunt_normalize_maps_company_lead(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)
    leads = await collector.normalize([SAMPLE_PRODUCT])
    assert len(leads) == 1
    assert leads[0].website == "https://www.acme.com/"
    assert leads[0].source == "producthunt"
    assert leads[0].metadata["website_resolution_failed"] is False


@pytest.mark.asyncio
async def test_producthunt_normalize_skips_missing_website(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)
    leads = await collector.normalize([{**SAMPLE_PRODUCT, "website": ""}])
    assert leads == []


@pytest.mark.asyncio
async def test_producthunt_normalize_keeps_redirect_when_resolution_fails(
    test_db: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
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
        patch("app.collectors.producthunt.producthunt_browser_page") as browser_ctx,
        patch(
            "app.collectors.producthunt.resolve_company_website",
            new=AsyncMock(
                return_value=WebsiteResolution(
                    website="https://www.producthunt.com/r/YVXYQHUZQFWTKE",
                    resolved=False,
                )
            ),
        ),
        caplog.at_level("INFO"),
    ):
        page = MagicMock()
        browser_ctx.return_value.__aenter__ = AsyncMock(return_value=page)
        browser_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        leads = await collector.normalize([redirect_product])

    assert len(leads) == 1
    assert leads[0].website == "https://www.producthunt.com/r/YVXYQHUZQFWTKE"
    assert leads[0].metadata["website_resolution_failed"] is True
    assert leads[0].metadata["website_redirect"] == "https://www.producthunt.com/r/YVXYQHUZQFWTKE"
    assert leads[0].metadata["product_hunt_url"] == redirect_product["url"]
    assert any("websites_unresolved=1" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_producthunt_normalize_continues_after_cloudflare(
    test_db: Any,
) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)
    products = [
        {
            **SAMPLE_PRODUCT,
            "id": "1",
            "name": "One",
            "website": "https://www.producthunt.com/r/ONE",
            "url": "https://www.producthunt.com/products/one",
        },
        {
            **SAMPLE_PRODUCT,
            "id": "2",
            "name": "Two",
            "website": "https://www.producthunt.com/r/TWO",
            "url": "https://www.producthunt.com/products/two",
        },
    ]

    async def resolve_side_effect(
        website: str,
        *,
        product_page_url: str | None = None,
        page: Any = None,
        timeout_s: float | None = None,
    ) -> WebsiteResolution:
        return WebsiteResolution(website=website, resolved=False)

    with (
        patch(
            "app.collectors.producthunt.raw_items_need_website_resolution",
            return_value=True,
        ),
        patch("app.collectors.producthunt.producthunt_browser_page") as browser_ctx,
        patch(
            "app.collectors.producthunt.resolve_company_website",
            new=AsyncMock(side_effect=resolve_side_effect),
        ),
        patch("app.collectors.producthunt.is_cloudflare_blocked", side_effect=[False, True]),
    ):
        page = MagicMock()
        browser_ctx.return_value.__aenter__ = AsyncMock(return_value=page)
        browser_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        leads = await collector.normalize(products)

    assert len(leads) == 2
    assert all(lead.metadata["website_resolution_failed"] for lead in leads)
    valid = await collector.validate(leads)
    assert len(valid) == 2


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
    assert not is_producthunt_redirect("https://www.acme.com/")
    assert not is_producthunt_redirect("https://www.producthunt.com/products/acme")


def test_is_external_company_url() -> None:
    assert is_external_company_url("https://www.softam.net/?ref=producthunt")
    assert not is_external_company_url("https://cloudflare.com/")
    assert not is_external_company_url("https://www.producthunt.com/r/abc")
    assert not is_external_company_url("https://lu.ma/producthunt")


def test_is_intermediate_host() -> None:
    assert is_intermediate_host("https://challenges.cloudflare.com/cdn-cgi/challenge")
    assert not is_intermediate_host("https://softam.net/")


def test_strip_tracking_params() -> None:
    raw = "https://www.producthunt.com/r/ABC?utm_campaign=producthunt-api"
    assert strip_tracking_params(raw) == "https://www.producthunt.com/r/ABC"
    assert (
        strip_tracking_params("https://www.softam.net/?ref=producthunt&utm_source=x")
        == "https://www.softam.net/"
    )


def _mock_locator(*, href: str | None = None, count: int = 1) -> MagicMock:
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    locator.get_attribute = AsyncMock(return_value=href)
    locator.first = locator
    return locator


def _mock_page() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.title = AsyncMock(return_value="HEHIMU, LLC | Product Hunt")
    page.content = AsyncMock(return_value="<html><body>debug</body></html>")
    page.wait_for_function = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    page.url = "https://www.producthunt.com/products/hehimu-llc"
    page.get_by_role = MagicMock(return_value=_mock_locator(count=0))
    page.evaluate = AsyncMock(return_value=False)
    page.locator = MagicMock(return_value=_mock_locator(count=0))
    return page


@pytest.mark.asyncio
async def test_page_has_cloudflare_challenge_by_title() -> None:
    page = _mock_page()
    page.title = AsyncMock(return_value="Just a moment...")
    assert await page_has_cloudflare_challenge(page) is True


@pytest.mark.asyncio
async def test_extract_via_visit_button() -> None:
    page = _mock_page()

    def locator_side_effect(selector: str) -> MagicMock:
        if selector == 'a[data-test="visit-website-button"]':
            return _mock_locator(href="https://www.softam.net/?ref=producthunt")
        return _mock_locator(count=0)

    page.locator = MagicMock(side_effect=locator_side_effect)
    result = await extract_via_visit_button(page, "https://www.producthunt.com/products/hehimu-llc")
    assert result == "https://www.softam.net/"


@pytest.mark.asyncio
async def test_extract_via_external_links() -> None:
    page = _mock_page()
    anchors = MagicMock()
    anchors.count = AsyncMock(return_value=2)
    anchors.nth = MagicMock(
        side_effect=[
            MagicMock(get_attribute=AsyncMock(return_value="https://twitter.com/x")),
            MagicMock(get_attribute=AsyncMock(return_value="https://nurevo.ai/")),
        ]
    )
    page.locator = MagicMock(return_value=anchors)
    result = await extract_via_external_links(page, "https://www.producthunt.com/products/nurevo")
    assert result == "https://nurevo.ai/"


@pytest.mark.asyncio
async def test_extract_via_json_ld() -> None:
    page = _mock_page()
    page.evaluate = AsyncMock(
        return_value=['{"@type":"WebApplication","url":"https://codexhelper.dev","name":"Codex"}']
    )
    result = await extract_via_json_ld(page)
    assert result == "https://codexhelper.dev"


@pytest.mark.asyncio
async def test_extract_via_next_data() -> None:
    page = _mock_page()
    page.evaluate = AsyncMock(
        return_value={"props": {"pageProps": {"websiteUrl": "https://web2ui.app"}}}
    )
    result = await extract_via_next_data(page)
    assert result == "https://web2ui.app"


@pytest.mark.asyncio
async def test_extract_via_meta_tags() -> None:
    page = _mock_page()
    page.evaluate = AsyncMock(
        return_value={
            "og:url": "https://shelfspace.io",
            "canonical": "https://www.producthunt.com/x",
        }
    )
    result = await extract_via_meta_tags(page)
    assert result == "https://shelfspace.io"


@pytest.mark.asyncio
async def test_resolve_company_website_returns_unresolved_on_timeout() -> None:
    async def slow_resolve(*args: Any, **kwargs: Any) -> WebsiteResolution:
        import asyncio

        await asyncio.sleep(10)
        return WebsiteResolution(website="https://never.example", resolved=True)

    with patch(
        "app.collectors.producthunt_redirect._resolve_within_budget",
        new=slow_resolve,
    ):
        result = await resolve_company_website(
            "https://www.producthunt.com/r/ABC",
            product_page_url="https://www.producthunt.com/products/x",
            page=None,
            timeout_s=0.05,
        )

    assert result.resolved is False
    assert result.website == "https://www.producthunt.com/r/ABC"


@pytest.mark.asyncio
async def test_resolve_company_website_skips_non_redirect() -> None:
    result = await resolve_company_website(
        "https://www.acme.com/",
        product_page_url="https://www.producthunt.com/products/acme",
        page=MagicMock(),
    )
    assert result.resolved is True
    assert result.website == "https://www.acme.com/"


@pytest.mark.asyncio
async def test_resolve_company_website_http_success() -> None:
    with patch(
        "app.collectors.producthunt_redirect.resolve_redirect_via_http",
        new=AsyncMock(return_value="https://resolved.example/"),
    ):
        result = await resolve_company_website(
            "https://www.producthunt.com/r/ABC",
            product_page_url="https://www.producthunt.com/products/x",
            page=None,
            timeout_s=5,
        )
    assert result.resolved is True
    assert result.website == "https://resolved.example/"
    assert result.source == "http_redirect"


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
        patch("app.collectors.producthunt.producthunt_browser_page") as browser_ctx,
        patch(
            "app.collectors.producthunt.resolve_company_website",
            new=AsyncMock(
                return_value=WebsiteResolution(
                    website="https://www.softam.net/",
                    resolved=True,
                    source="visit_button",
                )
            ),
        ) as resolve_mock,
    ):
        page = MagicMock()
        browser_ctx.return_value.__aenter__ = AsyncMock(return_value=page)
        browser_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        leads = await collector.normalize([redirect_product])

    assert len(leads) == 1
    assert leads[0].website == "https://www.softam.net/"
    assert leads[0].metadata["website_resolution_failed"] is False
    resolve_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_producthunt_browser_session_failure_still_returns_leads(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = ProductHuntCollector(service)
    redirect_product = {
        **SAMPLE_PRODUCT,
        "website": "https://www.producthunt.com/r/FAILSAFE",
    }

    class Boom:
        async def __aenter__(self) -> Any:
            raise RuntimeError("browser crashed")

        async def __aexit__(self, *args: Any) -> None:
            return None

    with (
        patch(
            "app.collectors.producthunt.raw_items_need_website_resolution",
            return_value=True,
        ),
        patch("app.collectors.producthunt.producthunt_browser_page", return_value=Boom()),
        patch(
            "app.collectors.producthunt.resolve_company_website",
            new=AsyncMock(
                return_value=WebsiteResolution(
                    website="https://www.producthunt.com/r/FAILSAFE",
                    resolved=False,
                )
            ),
        ),
    ):
        leads = await collector.normalize([redirect_product])

    assert len(leads) == 1
    assert leads[0].metadata["website_resolution_failed"] is True
