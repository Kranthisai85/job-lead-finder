from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.core.config import settings
from app.core.logger import get_logger
from app.utils.url import is_producthunt_redirect as _url_is_producthunt_redirect

logger = get_logger(__name__)

DEBUG_HTML_PATH = Path("/tmp/producthunt_debug.html")
_DEBUG_HTML_WRITTEN = False
_CF_BLOCKED = False

VISIT_LINK_SELECTORS: tuple[str, ...] = (
    'a[data-test="visit-website-button"]',
    'a[data-test="post-product-link"]',
    'a[data-test="product-link"]',
    'a[data-test="visit-button"]',
    'a[href*="producthunt.com/r/"]',
    'a[href^="/r/"]',
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

# Hard cap for any single website resolution attempt.
DEFAULT_RESOLVE_TIMEOUT_S = 5.0
# How long to wait for Cloudflare to clear before aborting (fail fast).
CF_DETECT_TIMEOUT_MS = 2_000


@dataclass(frozen=True, slots=True)
class WebsiteResolution:
    website: str
    resolved: bool
    source: str | None = None


def _resolve_timeout_s() -> float:
    configured = getattr(settings, "product_hunt_website_resolve_timeout", None)
    if configured is None:
        return DEFAULT_RESOLVE_TIMEOUT_S
    return float(configured)


def _reset_session_flags() -> None:
    global _DEBUG_HTML_WRITTEN, _CF_BLOCKED
    _DEBUG_HTML_WRITTEN = False
    _CF_BLOCKED = False


def _mark_cloudflare_blocked() -> None:
    global _CF_BLOCKED
    if not _CF_BLOCKED:
        logger.warning("producthunt_cloudflare_blocked aborting_further_browser_resolution=true")
    _CF_BLOCKED = True


def is_cloudflare_blocked() -> bool:
    return _CF_BLOCKED


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
    return _url_is_producthunt_redirect(url)


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
    return [cleaned]


async def _write_debug_html(page: Page, *, reason: str) -> None:
    global _DEBUG_HTML_WRITTEN
    if _DEBUG_HTML_WRITTEN:
        return
    try:
        html = await page.content()
        DEBUG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_HTML_PATH.write_text(html, encoding="utf-8")
        _DEBUG_HTML_WRITTEN = True
        title = ""
        with suppress(Exception):
            title = await page.title()
        logger.warning(
            "producthunt_debug_html_written path=%s reason=%s title=%s url=%s",
            DEBUG_HTML_PATH,
            reason,
            title,
            page.url,
        )
    except Exception as exc:
        logger.warning("producthunt_debug_html_failed error=%s", exc)


async def page_has_cloudflare_challenge(page: Page) -> bool:
    """Detect Cloudflare immediately from URL, title, or challenge HTML markers."""
    if is_intermediate_host(page.url):
        return True
    try:
        title = (await page.title()).lower()
    except Exception:
        title = ""
    if "just a moment" in title or "attention required" in title:
        return True
    try:
        has_challenge = await page.evaluate(
            """() => {
                const html = (document.documentElement && document.documentElement.innerHTML) || '';
                return html.includes('cf-browser-verification')
                    || html.includes('challenge-platform')
                    || html.includes('cf-challenge')
                    || html.includes('cdn-cgi/challenge');
            }"""
        )
        return bool(has_challenge)
    except Exception:
        return False


async def resolve_redirect_via_http(redirect_url: str, *, timeout_s: float) -> str | None:
    cleaned = strip_tracking_params(redirect_url)
    if not is_producthunt_redirect(cleaned):
        return None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    timeout = httpx.Timeout(max(0.5, timeout_s))
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            response = await client.get(cleaned, headers=headers)
            location = response.headers.get("location") or response.headers.get("Location")
            if location:
                absolute = strip_tracking_params(_absolute_url(location, cleaned))
                if is_external_company_url(absolute):
                    return absolute
    except Exception as exc:
        logger.debug("producthunt_http_redirect_failed url=%s error=%s", cleaned, exc)
    return None


@asynccontextmanager
async def producthunt_browser_page() -> AsyncIterator[Page]:
    """Yield a Playwright page; always close browser/context to avoid TargetClosedError."""
    _reset_session_flags()
    playwright_cm = async_playwright()
    playwright = await playwright_cm.__aenter__()
    browser: Browser | None = None
    context: BrowserContext | None = None
    try:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()
        yield page
    finally:
        if context is not None:
            with suppress(Exception):
                await context.close()
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        with suppress(Exception):
            await playwright_cm.__aexit__(None, None, None)


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
    return None


async def extract_via_external_links(page: Page, base_url: str) -> str | None:
    anchors = page.locator("a[href]")
    try:
        count = await anchors.count()
    except Exception:
        return None
    for index in range(min(count, 40)):
        try:
            href = await anchors.nth(index).get_attribute("href")
        except Exception:
            continue
        if not href:
            continue
        absolute = strip_tracking_params(_absolute_url(href, base_url))
        if is_external_company_url(absolute):
            return absolute
    return None


def _walk_for_website_candidate(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            if isinstance(value, str) and any(
                token in key_l for token in ("website", "url", "href", "link")
            ):
                cleaned = strip_tracking_params(value)
                if is_external_company_url(cleaned) or is_producthunt_redirect(cleaned):
                    return cleaned
            found = _walk_for_website_candidate(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _walk_for_website_candidate(item)
            if found:
                return found
    return None


async def extract_via_next_data(page: Page) -> str | None:
    try:
        data = await page.evaluate(
            """() => {
                const el = document.querySelector('#__NEXT_DATA__');
                if (!el || !el.textContent) return null;
                try { return JSON.parse(el.textContent); } catch (e) { return null; }
            }"""
        )
    except Exception:
        return None
    return _walk_for_website_candidate(data)


async def extract_via_json_ld(page: Page) -> str | None:
    try:
        scripts = await page.evaluate(
            """() => Array.from(
                document.querySelectorAll('script[type="application/ld+json"]')
            ).map(s => s.textContent || '')"""
        )
    except Exception:
        return None
    if not isinstance(scripts, list):
        return None
    for raw in scripts:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _walk_for_website_candidate(data)
        if found and is_external_company_url(found):
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


async def _quick_extract_from_loaded_page(page: Page, product_url: str) -> str | None:
    strategies: list[tuple[str, Any]] = [
        ("visit_button", lambda: extract_via_visit_button(page, product_url)),
        ("external_links", lambda: extract_via_external_links(page, product_url)),
        ("json_ld", lambda: extract_via_json_ld(page)),
        ("next_data", lambda: extract_via_next_data(page)),
        ("meta_tags", lambda: extract_via_meta_tags(page)),
    ]
    for source, run_strategy in strategies:
        try:
            candidate = await run_strategy()
        except Exception as exc:
            logger.debug("producthunt_strategy_failed source=%s error=%s", source, exc)
            continue
        if not candidate:
            continue
        if is_external_company_url(candidate):
            logger.info(
                "producthunt_website_extracted source=%s website=%s",
                source,
                candidate,
            )
            return str(candidate)
        if is_producthunt_redirect(candidate):
            # Nested /r/ on the page — treat as unresolved for this strategy.
            continue
    return None


async def _extract_via_playwright(
    page: Page,
    *,
    product_page_url: str | None,
    fallback_website: str,
    timeout_s: float,
) -> WebsiteResolution | None:
    if _CF_BLOCKED:
        return None

    goto_timeout_ms = max(1_000, int(timeout_s * 1000))
    targets: list[str] = []
    if product_page_url and product_page_url.strip():
        targets.extend(product_page_candidates(product_page_url))
    if is_producthunt_redirect(fallback_website):
        targets.append(strip_tracking_params(fallback_website))

    seen: set[str] = set()
    for target in targets:
        if target in seen or _CF_BLOCKED:
            continue
        seen.add(target)
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=goto_timeout_ms)
        except Exception as exc:
            logger.debug("producthunt_goto_failed url=%s error=%s", target, exc)
            continue

        # Give the challenge page a brief moment to paint, then abort immediately.
        with suppress(Exception):
            await page.wait_for_timeout(min(500, CF_DETECT_TIMEOUT_MS))

        if await page_has_cloudflare_challenge(page):
            await _write_debug_html(page, reason="cloudflare_challenge")
            _mark_cloudflare_blocked()
            title = ""
            with suppress(Exception):
                title = await page.title()
            logger.warning(
                "producthunt_cloudflare_detected title=%s url=%s aborting=true",
                title,
                page.url,
            )
            return None

        if is_external_company_url(page.url):
            website = strip_tracking_params(page.url)
            logger.info(
                "producthunt_website_extracted source=playwright_redirect website=%s",
                website,
            )
            return WebsiteResolution(website=website, resolved=True, source="playwright_redirect")

        extracted = await _quick_extract_from_loaded_page(page, target)
        if extracted:
            return WebsiteResolution(
                website=extracted,
                resolved=True,
                source="playwright_dom",
            )
    return None


async def _resolve_within_budget(
    website: str,
    *,
    product_page_url: str | None,
    page: Page | None,
    timeout_s: float,
) -> WebsiteResolution:
    cleaned = strip_tracking_params(website.strip())
    if not cleaned:
        return WebsiteResolution(website=website, resolved=False)

    if not is_producthunt_redirect(cleaned) and not is_intermediate_host(cleaned):
        return WebsiteResolution(website=cleaned, resolved=True, source="direct")

    original = cleaned
    deadline = asyncio.get_running_loop().time() + timeout_s

    def _remaining() -> float:
        return max(0.1, deadline - asyncio.get_running_loop().time())

    http_hit = await resolve_redirect_via_http(original, timeout_s=_remaining())
    if http_hit:
        logger.info(
            "producthunt_website_extracted source=http_redirect website=%s",
            http_hit,
        )
        return WebsiteResolution(website=http_hit, resolved=True, source="http_redirect")

    if page is None or _CF_BLOCKED:
        return WebsiteResolution(website=original, resolved=False)

    playwright_result = await _extract_via_playwright(
        page,
        product_page_url=product_page_url,
        fallback_website=original,
        timeout_s=_remaining(),
    )
    if playwright_result is not None:
        return playwright_result

    return WebsiteResolution(website=original, resolved=False)


async def resolve_company_website(
    website: str,
    *,
    product_page_url: str | None = None,
    page: Page | None = None,
    timeout_s: float | None = None,
) -> WebsiteResolution:
    """Best-effort website resolution with a hard timeout. Never raises for CF/timeouts."""
    budget = _resolve_timeout_s() if timeout_s is None else float(timeout_s)
    cleaned = website.strip()
    if not cleaned:
        return WebsiteResolution(website=website, resolved=False)
    original = strip_tracking_params(cleaned)

    try:
        return await asyncio.wait_for(
            _resolve_within_budget(
                original,
                product_page_url=product_page_url,
                page=page,
                timeout_s=budget,
            ),
            timeout=budget,
        )
    except TimeoutError:
        logger.warning(
            "producthunt_website_resolve_timeout website=%s timeout_s=%.1f",
            original,
            budget,
        )
        return WebsiteResolution(website=original, resolved=False)
    except Exception as exc:
        logger.warning(
            "producthunt_website_resolve_failed website=%s error=%s",
            original,
            exc,
        )
        return WebsiteResolution(website=original, resolved=False)


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
