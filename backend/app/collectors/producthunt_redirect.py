from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, Page, async_playwright

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

VISIT_LINK_SELECTORS: tuple[str, ...] = (
    'a[data-test="post-product-link"]',
    'a[data-test="visit-website-button"]',
    'a[data-test="product-link"]',
    'a[data-test="visit-button"]',
)

VISIT_LINK_NAMES: tuple[str, ...] = (
    "Visit website",
    "Get it",
    "Website",
    "Visit",
)

BLOCKED_EXTERNAL_HOSTS: frozenset[str] = frozenset(
    {
        "twitter.com",
        "x.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "youtu.be",
        "github.com",
        "apps.apple.com",
        "play.google.com",
    }
)


def _hostname(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_producthunt_host(url: str) -> bool:
    host = _hostname(url)
    return host == "producthunt.com" or host.endswith(".producthunt.com")


def is_producthunt_redirect(url: str) -> bool:
    """Return True when *url* is a Product Hunt short redirect (/r/...)."""
    cleaned = url.strip()
    if not cleaned or not is_producthunt_host(cleaned):
        return False
    return urlparse(cleaned).path.startswith("/r/")


def is_external_company_url(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return False
    if is_producthunt_host(cleaned):
        return False
    host = _hostname(cleaned)
    if not host or host in BLOCKED_EXTERNAL_HOSTS:
        return False
    return True


def _absolute_url(href: str, base_url: str) -> str:
    return urljoin(base_url, href.strip())


@asynccontextmanager
async def producthunt_browser_page() -> AsyncIterator[Page]:
    """Yield a shared Playwright page for Product Hunt website extraction."""
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            yield page
        finally:
            await browser.close()


async def _goto(page: Page, url: str) -> None:
    timeout_ms = int(settings.product_hunt_timeout * 1000)
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)


async def _read_href(page: Page, selector: str) -> str | None:
    locator = page.locator(selector).first
    if await locator.count() == 0:
        return None
    href = await locator.get_attribute("href")
    if not href:
        return None
    return href.strip()


async def _find_visit_href(page: Page) -> str | None:
    for selector in VISIT_LINK_SELECTORS:
        href = await _read_href(page, selector)
        if href:
            return href

    for name in VISIT_LINK_NAMES:
        locator = page.get_by_role("link", name=name).first
        try:
            if await locator.count() == 0:
                continue
            href = await locator.get_attribute("href")
            if href and href.strip():
                return href.strip()
        except Exception:
            continue
    return None


async def _find_external_href(page: Page, base_url: str) -> str | None:
    anchors = page.locator("a[href]")
    count = await anchors.count()
    for index in range(min(count, 100)):
        href = await anchors.nth(index).get_attribute("href")
        if not href:
            continue
        absolute = _absolute_url(href, base_url)
        if is_external_company_url(absolute):
            return absolute
    return None


async def _follow_redirect_with_playwright(page: Page, redirect_url: str) -> str | None:
    """Navigate a /r/ URL in Playwright and return the final destination if external."""
    try:
        await _goto(page, redirect_url)
        final_url = page.url.strip()
        if is_external_company_url(final_url):
            return final_url
        return None
    except Exception as exc:
        logger.warning(
            "producthunt_playwright_redirect_failed url=%s error=%s",
            redirect_url,
            exc,
        )
        return None


async def extract_website_from_product_page(
    product_page_url: str,
    *,
    page: Page,
    fallback_website: str,
) -> str:
    """Load a Product Hunt product page and extract the company website."""
    cleaned_product_url = product_page_url.strip()
    if not cleaned_product_url:
        return fallback_website

    try:
        await _goto(page, cleaned_product_url)
    except Exception as exc:
        logger.warning(
            "producthunt_product_page_load_failed url=%s error=%s",
            cleaned_product_url,
            exc,
        )
        return fallback_website

    try:
        visit_href = await _find_visit_href(page)
        if visit_href:
            absolute = _absolute_url(visit_href, cleaned_product_url)
            if is_external_company_url(absolute):
                logger.info(
                    "producthunt_website_extracted source=visit_link product=%s website=%s",
                    cleaned_product_url,
                    absolute,
                )
                return absolute
            if is_producthunt_redirect(absolute):
                followed = await _follow_redirect_with_playwright(page, absolute)
                if followed:
                    logger.info(
                        "producthunt_website_extracted source=visit_redirect "
                        "product=%s website=%s",
                        cleaned_product_url,
                        followed,
                    )
                    return followed

        external = await _find_external_href(page, cleaned_product_url)
        if external:
            logger.info(
                "producthunt_website_extracted source=external_link product=%s website=%s",
                cleaned_product_url,
                external,
            )
            return external
    except Exception as exc:
        logger.warning(
            "producthunt_website_extract_failed product=%s error=%s",
            cleaned_product_url,
            exc,
        )
        return fallback_website

    logger.warning(
        "producthunt_website_not_found product=%s fallback=%s",
        cleaned_product_url,
        fallback_website,
    )
    return fallback_website


async def resolve_company_website(
    website: str,
    *,
    product_page_url: str | None = None,
    page: Page | None = None,
) -> str:
    """Resolve Product Hunt /r/ websites via the product page when needed.

    Non-redirect websites are returned unchanged. Failures fall back to the
    original website value and never raise.
    """
    cleaned = website.strip()
    if not cleaned:
        return website
    if not is_producthunt_redirect(cleaned):
        return cleaned

    if not product_page_url or not str(product_page_url).strip():
        logger.warning(
            "producthunt_redirect_missing_product_url website=%s",
            cleaned,
        )
        return cleaned

    if page is not None:
        return await extract_website_from_product_page(
            str(product_page_url),
            page=page,
            fallback_website=cleaned,
        )

    try:
        async with producthunt_browser_page() as owned_page:
            return await extract_website_from_product_page(
                str(product_page_url),
                page=owned_page,
                fallback_website=cleaned,
            )
    except Exception as exc:
        logger.warning(
            "producthunt_playwright_unavailable website=%s error=%s",
            cleaned,
            exc,
        )
        return cleaned


def raw_items_need_website_resolution(raw_items: list[Any]) -> bool:
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        website = item.get("website")
        if website and is_producthunt_redirect(str(website)):
            return True
    return False
