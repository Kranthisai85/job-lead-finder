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

# Hosts that appear during Product Hunt redirect chains but are never the company site.
INTERMEDIATE_HOSTS: frozenset[str] = frozenset(
    {
        "cloudflare.com",
        "challenges.cloudflare.com",
        "cdnjs.cloudflare.com",
        "cloudflareinsights.com",
        "cf-ipfs.com",
    }
)

REDIRECT_SETTLE_POLL_MS = 400
REDIRECT_STABLE_POLLS = 3


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


def is_intermediate_host(url: str) -> bool:
    """Return True for Cloudflare / challenge / CDN hops that are not company sites."""
    host = _hostname(url)
    if not host:
        return False
    if host in INTERMEDIATE_HOSTS:
        return True
    if host.endswith(".cloudflare.com"):
        return True
    if host.endswith(".cloudflareinsights.com"):
        return True
    path = urlparse(url.strip()).path.lower()
    return "/cdn-cgi/" in path


def is_external_company_url(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return False
    if is_producthunt_host(cleaned):
        return False
    if is_intermediate_host(cleaned):
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


def _walk_for_website_candidate(value: Any, *, depth: int = 0) -> str | None:
    """Search nested JSON (e.g. __NEXT_DATA__) for a usable company website."""
    if depth > 8 or value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if is_external_company_url(cleaned):
            return cleaned
        return None
    if isinstance(value, dict):
        preferred_keys = (
            "website",
            "websiteUrl",
            "website_url",
            "productUrl",
            "product_url",
            "url",
            "href",
        )
        for key in preferred_keys:
            if key in value:
                found = _walk_for_website_candidate(value.get(key), depth=depth + 1)
                if found:
                    return found
        for nested in value.values():
            found = _walk_for_website_candidate(nested, depth=depth + 1)
            if found:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _walk_for_website_candidate(item, depth=depth + 1)
            if found:
                return found
    return None


async def _extract_from_next_data(page: Page) -> str | None:
    try:
        payload = await page.evaluate(
            """() => {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el || !el.textContent) return null;
                try { return JSON.parse(el.textContent); } catch (e) { return null; }
            }"""
        )
    except Exception:
        return None
    return _walk_for_website_candidate(payload)


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


async def _wait_for_company_url(page: Page, *, timeout_ms: int) -> str | None:
    """Poll until navigation leaves Product Hunt / Cloudflare intermediates."""
    elapsed = 0
    stable_hits = 0
    last_url = page.url.strip()

    while elapsed < timeout_ms:
        current = page.url.strip()
        if is_external_company_url(current):
            if current == last_url:
                stable_hits += 1
                if stable_hits >= REDIRECT_STABLE_POLLS:
                    return current
            else:
                stable_hits = 1
                last_url = current
        else:
            stable_hits = 0
            last_url = current
            if is_intermediate_host(current) or is_producthunt_host(current):
                logger.debug(
                    "producthunt_redirect_waiting current=%s elapsed_ms=%d",
                    current,
                    elapsed,
                )

        await page.wait_for_timeout(REDIRECT_SETTLE_POLL_MS)
        elapsed += REDIRECT_SETTLE_POLL_MS

    final_url = page.url.strip()
    if is_external_company_url(final_url):
        return final_url
    return None


def _candidate_from_redirect_chain(locations: list[str]) -> str | None:
    """Prefer the last non-intermediate external URL seen in the redirect chain."""
    for location in reversed(locations):
        if is_external_company_url(location):
            return location
    return None


async def _follow_redirect_with_playwright(page: Page, redirect_url: str) -> str | None:
    """Navigate a /r/ URL and resolve past Cloudflare to the company domain."""
    timeout_ms = int(settings.product_hunt_timeout * 1000)
    redirect_locations: list[str] = []

    def _on_response(response: Any) -> None:
        try:
            status = int(getattr(response, "status", 0) or 0)
            headers = getattr(response, "headers", {}) or {}
            location = headers.get("location") or headers.get("Location")
            if status in {301, 302, 303, 307, 308} and location:
                absolute = _absolute_url(str(location), str(response.url))
                redirect_locations.append(absolute)
            response_url = str(getattr(response, "url", "") or "")
            if response_url:
                redirect_locations.append(response_url)
        except Exception:
            return

    page.on("response", _on_response)
    try:
        await page.goto(redirect_url, wait_until="domcontentloaded", timeout=timeout_ms)
        waited = await _wait_for_company_url(page, timeout_ms=timeout_ms)
        if waited:
            return waited

        chain_candidate = _candidate_from_redirect_chain(redirect_locations)
        if chain_candidate:
            logger.info(
                "producthunt_redirect_chain_candidate url=%s",
                chain_candidate,
            )
            return chain_candidate

        final_url = page.url.strip()
        if is_intermediate_host(final_url):
            logger.warning(
                "producthunt_redirect_stopped_on_intermediate url=%s",
                final_url,
            )
            return None
        if is_external_company_url(final_url):
            return final_url
        return None
    except Exception as exc:
        logger.warning(
            "producthunt_playwright_redirect_failed url=%s error=%s",
            redirect_url,
            exc,
        )
        chain_candidate = _candidate_from_redirect_chain(redirect_locations)
        if chain_candidate:
            return chain_candidate
        return None
    finally:
        try:
            page.remove_listener("response", _on_response)
        except Exception:
            pass


def _safe_fallback(fallback_website: str) -> str:
    """Never return Product Hunt redirects or Cloudflare hosts as the company site."""
    if not fallback_website.strip():
        return ""
    if is_producthunt_redirect(fallback_website) or is_intermediate_host(fallback_website):
        return ""
    return fallback_website


async def extract_website_from_product_page(
    product_page_url: str,
    *,
    page: Page,
    fallback_website: str,
) -> str:
    """Load a Product Hunt product page and extract the company website."""
    cleaned_product_url = product_page_url.strip()
    if not cleaned_product_url:
        return _safe_fallback(fallback_website)

    try:
        await _goto(page, cleaned_product_url)
    except Exception as exc:
        logger.warning(
            "producthunt_product_page_load_failed url=%s error=%s",
            cleaned_product_url,
            exc,
        )
        return _safe_fallback(fallback_website)

    try:
        next_data_website = await _extract_from_next_data(page)
        if next_data_website:
            logger.info(
                "producthunt_website_extracted source=next_data product=%s website=%s",
                cleaned_product_url,
                next_data_website,
            )
            return next_data_website

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
                logger.warning(
                    "producthunt_visit_redirect_unresolved product=%s redirect=%s",
                    cleaned_product_url,
                    absolute,
                )

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
        return _safe_fallback(fallback_website)

    logger.warning(
        "producthunt_website_not_found product=%s fallback=%s",
        cleaned_product_url,
        fallback_website,
    )
    return _safe_fallback(fallback_website)


async def resolve_company_website(
    website: str,
    *,
    product_page_url: str | None = None,
    page: Page | None = None,
) -> str:
    """Resolve Product Hunt /r/ websites via the product page when needed.

    Non-redirect websites are returned unchanged unless they are intermediate
    hosts (e.g. cloudflare.com). Failures fall back carefully and never raise.
    """
    cleaned = website.strip()
    if not cleaned:
        return website

    if is_intermediate_host(cleaned):
        logger.warning("producthunt_reject_intermediate_website website=%s", cleaned)
        if product_page_url and str(product_page_url).strip():
            # Try to recover from a bad previously-stored Cloudflare URL.
            pass
        else:
            return ""

    if not is_producthunt_redirect(cleaned) and not is_intermediate_host(cleaned):
        return cleaned

    if not product_page_url or not str(product_page_url).strip():
        logger.warning(
            "producthunt_redirect_missing_product_url website=%s",
            cleaned,
        )
        return (
            "" if (is_producthunt_redirect(cleaned) or is_intermediate_host(cleaned)) else cleaned
        )

    fallback = cleaned if is_producthunt_redirect(cleaned) else ""

    if page is not None:
        return await extract_website_from_product_page(
            str(product_page_url),
            page=page,
            fallback_website=fallback or cleaned,
        )

    try:
        async with producthunt_browser_page() as owned_page:
            return await extract_website_from_product_page(
                str(product_page_url),
                page=owned_page,
                fallback_website=fallback or cleaned,
            )
    except Exception as exc:
        logger.warning(
            "producthunt_playwright_unavailable website=%s error=%s",
            cleaned,
            exc,
        )
        return ""


def raw_items_need_website_resolution(raw_items: list[Any]) -> bool:
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        website = item.get("website")
        if not website:
            continue
        website_str = str(website)
        if is_producthunt_redirect(website_str) or is_intermediate_host(website_str):
            return True
    return False
