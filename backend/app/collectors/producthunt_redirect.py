from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import Browser, Page, async_playwright

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

DEBUG_HTML_PATH = Path("/tmp/producthunt_debug.html")
_DEBUG_HTML_WRITTEN = False

VISIT_LINK_SELECTORS: tuple[str, ...] = (
    'a[data-test="visit-website-button"]',
    'a[data-test="post-product-link"]',
    'a[data-test="product-link"]',
    'a[data-test="visit-button"]',
    'a[href*="producthunt.com/r/"]',
    'a[href^="/r/"]',
)

VISIT_LINK_NAMES: tuple[str, ...] = (
    "Visit website",
    "Go to website",
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
        "lu.ma",
    }
)

INTERMEDIATE_HOSTS: frozenset[str] = frozenset(
    {
        "cloudflare.com",
        "challenges.cloudflare.com",
        "cdnjs.cloudflare.com",
        "cloudflareinsights.com",
        "cf-ipfs.com",
    }
)

CHALLENGE_WAIT_MS = 45_000
PRODUCT_READY_SELECTORS = (
    'a[data-test="visit-website-button"], '
    'a[data-test="post-product-link"], '
    'a[href*="/r/"], '
    "#__NEXT_DATA__, "
    'script[type="application/ld+json"]'
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
    cleaned = url.strip()
    if not cleaned or not is_producthunt_host(cleaned):
        return False
    return urlparse(cleaned).path.startswith("/r/")


def is_intermediate_host(url: str) -> bool:
    host = _hostname(url)
    if not host:
        return False
    if host in INTERMEDIATE_HOSTS:
        return True
    if host.endswith(".cloudflare.com") or host.endswith(".cloudflareinsights.com"):
        return True
    return "/cdn-cgi/" in urlparse(url.strip()).path.lower()


def is_external_company_url(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return False
    if is_producthunt_host(cleaned) or is_intermediate_host(cleaned):
        return False
    host = _hostname(cleaned)
    return bool(host) and host not in BLOCKED_EXTERNAL_HOSTS


def strip_tracking_params(url: str) -> str:
    parsed = urlparse(url.strip())
    if is_producthunt_redirect(url) or is_producthunt_host(url):
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    # Keep company URLs clean of PH referral params.
    query_parts = [
        part
        for part in parsed.query.split("&")
        if part and not part.lower().startswith("utm_") and not part.lower().startswith("ref=")
    ]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "&".join(query_parts),
            "",
        )
    )


def _absolute_url(href: str, base_url: str) -> str:
    return urljoin(base_url, href.strip())


def product_page_candidates(product_page_url: str) -> list[str]:
    cleaned = strip_tracking_params(product_page_url)
    candidates = [cleaned]
    if "/products/" in cleaned:
        alt = cleaned.replace("/products/", "/posts/", 1)
        if alt not in candidates:
            candidates.append(alt)
    elif "/posts/" in cleaned:
        alt = cleaned.replace("/posts/", "/products/", 1)
        if alt not in candidates:
            candidates.append(alt)
    return candidates


def _safe_fallback(fallback_website: str) -> str:
    if not fallback_website.strip():
        return ""
    if is_producthunt_redirect(fallback_website) or is_intermediate_host(fallback_website):
        return ""
    return fallback_website


async def _write_debug_html(page: Page, *, reason: str) -> None:
    global _DEBUG_HTML_WRITTEN
    if _DEBUG_HTML_WRITTEN:
        return
    try:
        html = await page.content()
        DEBUG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_HTML_PATH.write_text(html, encoding="utf-8")
        _DEBUG_HTML_WRITTEN = True
        logger.warning(
            "producthunt_debug_html_written path=%s reason=%s title=%s url=%s",
            DEBUG_HTML_PATH,
            reason,
            await page.title(),
            page.url,
        )
    except Exception as exc:
        logger.warning("producthunt_debug_html_failed error=%s", exc)


async def _is_challenge_page(page: Page) -> bool:
    if is_intermediate_host(page.url):
        return True
    try:
        title = (await page.title()).lower()
    except Exception:
        return False
    return "just a moment" in title or "attention required" in title


async def _wait_for_challenge_clear(page: Page) -> bool:
    try:
        await page.wait_for_function(
            """() => {
                const title = (document.title || '').toLowerCase();
                return !title.includes('just a moment') && !title.includes('attention required');
            }""",
            timeout=CHALLENGE_WAIT_MS,
        )
        return True
    except Exception:
        return not await _is_challenge_page(page)


@asynccontextmanager
async def producthunt_browser_page() -> AsyncIterator[Page]:
    """Yield a shared Playwright page configured for Product Hunt."""
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1365, "height": 900},
                locale="en-US",
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = await context.new_page()
            # Warm homepage so Cloudflare challenge can clear once per session.
            try:
                await page.goto(
                    "https://www.producthunt.com/",
                    wait_until="domcontentloaded",
                    timeout=int(settings.product_hunt_timeout * 1000),
                )
                await _wait_for_challenge_clear(page)
            except Exception as exc:
                logger.warning("producthunt_warmup_failed error=%s", exc)
            yield page
        finally:
            await browser.close()


async def _goto_product_page(page: Page, url: str) -> bool:
    timeout_ms = int(settings.product_hunt_timeout * 1000)
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    cleared = await _wait_for_challenge_clear(page)
    if not cleared:
        await _write_debug_html(page, reason="cloudflare_challenge")
        return False
    try:
        await page.wait_for_selector(PRODUCT_READY_SELECTORS, timeout=15_000)
    except Exception:
        # Page may still be usable; continue to extraction strategies.
        pass
    return True


async def _read_href(page: Page, selector: str) -> str | None:
    locator = page.locator(selector).first
    if await locator.count() == 0:
        return None
    href = await locator.get_attribute("href")
    return href.strip() if href else None


async def extract_via_visit_button(page: Page, base_url: str) -> str | None:
    for selector in VISIT_LINK_SELECTORS:
        href = await _read_href(page, selector)
        if not href:
            continue
        absolute = strip_tracking_params(_absolute_url(href, base_url))
        if is_external_company_url(absolute):
            return absolute
        if is_producthunt_redirect(absolute):
            return absolute

    for name in VISIT_LINK_NAMES:
        locator = page.get_by_role("link", name=name).first
        try:
            if await locator.count() == 0:
                continue
            href = await locator.get_attribute("href")
            if not href:
                continue
            absolute = strip_tracking_params(_absolute_url(href, base_url))
            if is_external_company_url(absolute) or is_producthunt_redirect(absolute):
                return absolute
        except Exception:
            continue
    return None


async def extract_via_external_links(page: Page, base_url: str) -> str | None:
    anchors = page.locator("a[href]")
    count = await anchors.count()
    for index in range(min(count, 200)):
        href = await anchors.nth(index).get_attribute("href")
        if not href:
            continue
        absolute = strip_tracking_params(_absolute_url(href, base_url))
        if is_external_company_url(absolute):
            return absolute
    return None


def _walk_for_website_candidate(value: Any, *, depth: int = 0) -> str | None:
    if depth > 8 or value is None:
        return None
    if isinstance(value, str):
        cleaned = strip_tracking_params(value.strip())
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


async def extract_via_next_data(page: Page) -> str | None:
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


async def extract_via_json_ld(page: Page) -> str | None:
    try:
        payloads = await page.evaluate(
            """() => Array.from(
                document.querySelectorAll('script[type="application/ld+json"]')
            ).map(node => node.textContent || '')"""
        )
    except Exception:
        return None
    if not isinstance(payloads, list):
        return None
    for raw in payloads:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _walk_for_website_candidate(data)
        if found and not is_producthunt_host(found):
            return found
    return None


async def extract_via_meta_tags(page: Page) -> str | None:
    try:
        metas = await page.evaluate(
            """() => {
                const out = {};
                const nodes = document.querySelectorAll('meta[property], meta[name]');
                for (const m of Array.from(nodes)) {
                    const key = m.getAttribute('property') || m.getAttribute('name');
                    if (key) out[key] = m.getAttribute('content');
                }
                const canonical = document.querySelector('link[rel="canonical"]');
                if (canonical) out.canonical = canonical.getAttribute('href');
                return out;
            }"""
        )
    except Exception:
        return None
    if not isinstance(metas, dict):
        return None
    for key in ("og:url", "twitter:url", "canonical", "og:see_also"):
        value = metas.get(key)
        if isinstance(value, str):
            cleaned = strip_tracking_params(value)
            if is_external_company_url(cleaned):
                return cleaned
    return None


async def _follow_redirect_with_playwright(page: Page, redirect_url: str) -> str | None:
    cleaned = strip_tracking_params(redirect_url)
    timeout_ms = int(settings.product_hunt_timeout * 1000)
    redirect_locations: list[str] = []

    def _on_response(response: Any) -> None:
        try:
            status = int(getattr(response, "status", 0) or 0)
            headers = getattr(response, "headers", {}) or {}
            location = headers.get("location") or headers.get("Location")
            if status in {301, 302, 303, 307, 308} and location:
                redirect_locations.append(_absolute_url(str(location), str(response.url)))
            response_url = str(getattr(response, "url", "") or "")
            if response_url:
                redirect_locations.append(response_url)
        except Exception:
            return

    page.on("response", _on_response)
    try:
        await page.goto(cleaned, wait_until="domcontentloaded", timeout=timeout_ms)
        await _wait_for_challenge_clear(page)
        if is_external_company_url(page.url):
            return strip_tracking_params(page.url)
        for location in reversed(redirect_locations):
            if is_external_company_url(location):
                return strip_tracking_params(location)
        return None
    except Exception as exc:
        logger.warning(
            "producthunt_playwright_redirect_failed url=%s error=%s",
            cleaned,
            exc,
        )
        return None
    finally:
        try:
            page.remove_listener("response", _on_response)
        except Exception:
            pass


async def resolve_redirect_url(page: Page, redirect_url: str) -> str | None:
    cleaned = strip_tracking_params(redirect_url)
    if is_external_company_url(cleaned):
        return cleaned
    if not is_producthunt_redirect(cleaned):
        return None
    return await _follow_redirect_with_playwright(page, cleaned)


async def _maybe_resolve_candidate(page: Page, candidate: str | None, *, source: str) -> str | None:
    if not candidate:
        return None
    if is_external_company_url(candidate):
        logger.info("producthunt_website_extracted source=%s website=%s", source, candidate)
        return candidate
    if is_producthunt_redirect(candidate):
        followed = await resolve_redirect_url(page, candidate)
        if followed:
            logger.info(
                "producthunt_website_extracted source=%s website=%s via=redirect",
                source,
                followed,
            )
            return followed
    return None


async def extract_website_from_product_page(
    product_page_url: str,
    *,
    page: Page,
    fallback_website: str,
) -> str:
    """Extract company website from a Product Hunt product page using multiple strategies."""
    cleaned_product_url = strip_tracking_params(product_page_url)
    page_loaded = False
    for candidate_page in product_page_candidates(cleaned_product_url):
        try:
            if await _goto_product_page(page, candidate_page):
                cleaned_product_url = candidate_page
                page_loaded = True
                break
        except Exception as exc:
            logger.warning(
                "producthunt_product_page_load_failed url=%s error=%s",
                candidate_page,
                exc,
            )

    if not page_loaded:
        # Last chance: follow GraphQL /r/ URL with the warmed browser session.
        resolved = await _maybe_resolve_candidate(
            page,
            fallback_website if is_producthunt_redirect(fallback_website) else None,
            source="graphql_redirect",
        )
        if resolved:
            return resolved
        return _safe_fallback(fallback_website)

    strategies: list[tuple[str, Any]] = [
        ("visit_button", lambda: extract_via_visit_button(page, cleaned_product_url)),
        ("external_links", lambda: extract_via_external_links(page, cleaned_product_url)),
        ("json_ld", lambda: extract_via_json_ld(page)),
        ("next_data", lambda: extract_via_next_data(page)),
        ("meta_tags", lambda: extract_via_meta_tags(page)),
    ]

    for source, run_strategy in strategies:
        try:
            candidate = await run_strategy()
        except Exception as exc:
            logger.warning(
                "producthunt_strategy_failed source=%s error=%s",
                source,
                exc,
            )
            continue
        resolved = await _maybe_resolve_candidate(page, candidate, source=source)
        if resolved:
            return resolved

    if is_producthunt_redirect(fallback_website):
        resolved = await _maybe_resolve_candidate(
            page,
            fallback_website,
            source="graphql_redirect",
        )
        if resolved:
            return resolved

    await _write_debug_html(page, reason="website_not_found")
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
    cleaned = website.strip()
    if not cleaned:
        return website

    if not is_producthunt_redirect(cleaned) and not is_intermediate_host(cleaned):
        return cleaned

    if not product_page_url or not str(product_page_url).strip():
        if page is not None and is_producthunt_redirect(cleaned):
            followed = await resolve_redirect_url(page, cleaned)
            return followed or ""
        logger.warning("producthunt_redirect_missing_product_url website=%s", cleaned)
        return ""

    fallback = cleaned

    async def _run(active_page: Page) -> str:
        return await extract_website_from_product_page(
            str(product_page_url),
            page=active_page,
            fallback_website=fallback,
        )

    if page is not None:
        return await _run(page)

    try:
        async with producthunt_browser_page() as owned_page:
            return await _run(owned_page)
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
