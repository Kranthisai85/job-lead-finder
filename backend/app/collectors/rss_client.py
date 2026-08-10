"""Generic RSS / Atom feed client — free, no API key."""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _strip_html(value: str) -> str:
    return _HTML_TAG_RE.sub(" ", value or "").strip()


def parse_feed_xml(payload: str) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    tag = root.tag.lower()
    if tag.endswith("feed"):
        return _parse_atom(root)
    return _parse_rss(root)


def _parse_rss(root: ET.Element) -> list[dict[str, Any]]:
    channel = root.find("channel")
    if channel is None:
        channel = root
    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        description = _strip_html(_text(item.find("description")))
        pub_date = _text(item.find("pubDate"))
        # Google News often embeds the publisher URL in description HTML before strip.
        raw_description = ""
        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            raw_description = desc_el.text
        items.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "raw_description": raw_description,
                "published": pub_date,
            }
        )
    return items


def _parse_atom(root: ET.Element) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", _ATOM_NS) or root.findall("entry"):
        title_el = entry.find("atom:title", _ATOM_NS)
        if title_el is None:
            title_el = entry.find("title")
        title = _text(title_el)
        link = ""
        for link_el in entry.findall("atom:link", _ATOM_NS) or entry.findall("link"):
            href = link_el.attrib.get("href", "")
            rel = link_el.attrib.get("rel", "alternate")
            if href and rel in {"alternate", ""}:
                link = href
                break
            if href and not link:
                link = href
        summary_el = entry.find("atom:summary", _ATOM_NS)
        if summary_el is None:
            summary_el = entry.find("summary")
        content_el = entry.find("atom:content", _ATOM_NS)
        if content_el is None:
            content_el = entry.find("content")
        raw = (summary_el.text if summary_el is not None else "") or (
            content_el.text if content_el is not None else ""
        )
        updated_el = entry.find("atom:updated", _ATOM_NS) or entry.find("updated")
        items.append(
            {
                "title": title,
                "link": link,
                "description": _strip_html(raw or ""),
                "raw_description": raw or "",
                "published": _text(updated_el),
            }
        )
    return items


async def fetch_rss_items(
    feed_urls: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    headers = {"User-Agent": settings.rss_user_agent}
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.rss_timeout)
    items: list[dict[str, Any]] = []
    try:
        for feed_url in feed_urls:
            url = feed_url.strip()
            if not url:
                continue
            try:
                response = await http_client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                parsed = parse_feed_xml(response.text)
                for item in parsed:
                    item["feed_url"] = url
                items.extend(parsed)
                logger.info("collector=rss feed=%s items=%d", url, len(parsed))
            except Exception as exc:  # noqa: BLE001
                logger.warning("collector=rss feed=%s error=%s", url, exc)
    finally:
        if owns_client:
            await http_client.aclose()
    return items


def default_rss_feeds() -> list[str]:
    raw = settings.rss_feed_urls or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def default_google_news_feeds() -> list[str]:
    raw = settings.google_news_feed_urls or ""
    return [part.strip() for part in raw.split(",") if part.strip()]
