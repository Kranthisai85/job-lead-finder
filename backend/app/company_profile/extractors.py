from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.company_profile.names import clean_company_display_name
from app.crawler.types import SocialLinks, WebsiteProfile

CTA_PATTERN = re.compile(
    r"\b(start\s+free|get\s+started|try\s+(?:for\s+)?free|sign\s+up|"
    r"book\s+(?:a\s+)?demo|request\s+(?:a\s+)?demo|contact\s+sales|"
    r"start\s+trial|free\s+trial|subscribe|join\s+(?:now|free))\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
FOUNDED_PATTERN = re.compile(
    r"(?:founded|established|since)\s*(?:in\s*)?((?:19|20)\d{2})",
    re.IGNORECASE,
)
HEADQUARTERS_PATTERN = re.compile(
    r"(?:headquarters|based\s+in|located\s+in)\s*[:\-]?\s*([A-Za-z][A-Za-z\s,.\-]{2,60})",
    re.IGNORECASE,
)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _meta_content(
    soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None
) -> str | None:
    if name:
        tag = soup.find("meta", attrs={"name": name})
        if isinstance(tag, Tag):
            return _clean_text(str(tag.get("content", "")))
    if prop:
        tag = soup.find("meta", attrs={"property": prop})
        if isinstance(tag, Tag):
            return _clean_text(str(tag.get("content", "")))
    return None


def extract_html_soup(profile: WebsiteProfile) -> BeautifulSoup:
    html = str((profile.metadata or {}).get("html", ""))
    return BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")


def extract_company_name(profile: WebsiteProfile, soup: BeautifulSoup) -> str | None:
    og = (profile.metadata or {}).get("open_graph") or {}
    twitter = (profile.metadata or {}).get("twitter") or {}
    candidates = [
        og.get("og:site_name") if isinstance(og, dict) else None,
        og.get("og:title") if isinstance(og, dict) else None,
        twitter.get("twitter:title") if isinstance(twitter, dict) else None,
        profile.title,
        _meta_content(soup, prop="og:site_name"),
        _meta_content(soup, prop="og:title"),
        _meta_content(soup, name="twitter:title"),
    ]
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        candidates.append(h1.get_text(" ", strip=True))

    for item in candidates:
        cleaned = _clean_text(str(item) if item else None)
        if cleaned:
            cleaned = clean_company_display_name(cleaned)
            if cleaned:
                return cleaned
    return None


def extract_tagline(profile: WebsiteProfile, soup: BeautifulSoup) -> str | None:
    og = (profile.metadata or {}).get("open_graph") or {}
    twitter = (profile.metadata or {}).get("twitter") or {}
    candidates = [
        og.get("og:description") if isinstance(og, dict) else None,
        twitter.get("twitter:description") if isinstance(twitter, dict) else None,
        profile.description,
        _meta_content(soup, name="description"),
        _meta_content(soup, prop="og:description"),
        _meta_content(soup, name="twitter:description"),
    ]
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        sibling = h1.find_next(["p", "h2"])
        if isinstance(sibling, Tag):
            candidates.append(sibling.get_text(" ", strip=True))

    for item in candidates:
        cleaned = _clean_text(str(item) if item else None)
        if cleaned and 8 <= len(cleaned) <= 160:
            return cleaned
    return None


def extract_short_description(profile: WebsiteProfile, soup: BeautifulSoup) -> str | None:
    tagline = extract_tagline(profile, soup)
    if tagline:
        return tagline
    hero = extract_hero_text(soup)
    return _clean_text(hero[:240] if hero else None)


def extract_hero_text(soup: BeautifulSoup) -> str | None:
    selectors = (
        "header",
        "section.hero",
        "[class*='hero']",
        "main",
        "#hero",
    )
    chunks: list[str] = []
    for selector in selectors:
        node = soup.select_one(selector)
        if not isinstance(node, Tag):
            continue
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            chunks.append(text[:400])
            break
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        chunks.insert(0, h1.get_text(" ", strip=True))
    return _clean_text(" ".join(chunks)) if chunks else None


def extract_nav_text(soup: BeautifulSoup) -> str | None:
    nav = soup.find("nav")
    if not isinstance(nav, Tag):
        return None
    return _clean_text(nav.get_text(" ", strip=True))


def extract_footer_text(soup: BeautifulSoup) -> str | None:
    footer = soup.find("footer")
    if not isinstance(footer, Tag):
        return None
    return _clean_text(footer.get_text(" ", strip=True))


def extract_primary_cta(soup: BeautifulSoup) -> str | None:
    for selector in ("a", "button"):
        for node in soup.select(selector):
            text = _clean_text(node.get_text(" ", strip=True))
            if not text or len(text) > 40:
                continue
            if CTA_PATTERN.search(text):
                return text
    return None


def extract_json_ld_blocks(soup: BeautifulSoup) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))
    return blocks


def _walk_json_ld(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for block in blocks:
        items.append(block)
        graph = block.get("@graph")
        if isinstance(graph, list):
            items.extend(item for item in graph if isinstance(item, dict))
    return items


def extract_organization_fields(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in _walk_json_ld(extract_json_ld_blocks(soup)):
        types = item.get("@type")
        type_names = (
            {types} if isinstance(types, str) else set(types) if isinstance(types, list) else set()
        )
        if not type_names.intersection(
            {"Organization", "Corporation", "LocalBusiness", "SoftwareApplication"}
        ):
            continue
        if "name" in item and not result.get("name"):
            result["name"] = item.get("name")
        if "description" in item and not result.get("description"):
            result["description"] = item.get("description")
        if "foundingDate" in item and not result.get("foundingDate"):
            result["foundingDate"] = item.get("foundingDate")
        address = item.get("address")
        if isinstance(address, dict) and not result.get("headquarters"):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            result["headquarters"] = _clean_text(", ".join(str(part) for part in parts if part))
        elif isinstance(address, str) and not result.get("headquarters"):
            result["headquarters"] = _clean_text(address)
        offers = item.get("offers")
        if isinstance(offers, dict) and not result.get("price"):
            result["price"] = offers.get("price") or offers.get("category")
    return result


def extract_founded_year(soup: BeautifulSoup, org_fields: dict[str, Any]) -> int | None:
    founding = org_fields.get("foundingDate")
    if isinstance(founding, str):
        match = YEAR_PATTERN.search(founding)
        if match:
            return int(match.group(0))

    footer = extract_footer_text(soup) or ""
    hero = extract_hero_text(soup) or ""
    blob = f"{footer}\n{hero}"
    founded = FOUNDED_PATTERN.search(blob)
    if founded:
        return int(founded.group(1))
    return None


def extract_headquarters(soup: BeautifulSoup, org_fields: dict[str, Any]) -> str | None:
    hq = org_fields.get("headquarters")
    if isinstance(hq, str) and hq.strip():
        return hq.strip()
    footer = extract_footer_text(soup) or ""
    match = HEADQUARTERS_PATTERN.search(footer)
    if match:
        return _clean_text(match.group(1))
    return None


def extract_social_links(profile: WebsiteProfile) -> dict[str, list[str]]:
    social: SocialLinks = profile.social_links
    result: dict[str, list[str]] = {}
    mapping = {
        "linkedin": social.linkedin,
        "twitter": social.twitter,
        "github": social.github,
        "facebook": social.facebook,
        "instagram": social.instagram,
        "youtube": social.youtube,
    }
    for key, values in mapping.items():
        if values:
            result[key] = list(values)
    return result


def build_signal_corpus(profile: WebsiteProfile, soup: BeautifulSoup) -> str:
    og = (profile.metadata or {}).get("open_graph") or {}
    twitter = (profile.metadata or {}).get("twitter") or {}
    org = extract_organization_fields(soup)
    parts = [
        profile.title or "",
        profile.description or "",
        str(og.get("og:title", "")) if isinstance(og, dict) else "",
        str(og.get("og:description", "")) if isinstance(og, dict) else "",
        str(twitter.get("twitter:title", "")) if isinstance(twitter, dict) else "",
        str(twitter.get("twitter:description", "")) if isinstance(twitter, dict) else "",
        extract_hero_text(soup) or "",
        extract_nav_text(soup) or "",
        extract_footer_text(soup) or "",
        str(org.get("name") or ""),
        str(org.get("description") or ""),
        " ".join(profile.pricing_pages),
        " ".join(profile.documentation_pages),
    ]
    return " ".join(part for part in parts if part).lower()
