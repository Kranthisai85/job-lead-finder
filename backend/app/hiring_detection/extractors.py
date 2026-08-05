from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.hiring_detection.ats import detect_ats_provider, normalize_job_url
from app.hiring_detection.config import (
    EMPLOYMENT_TYPE_KEYWORDS,
    ENGINEERING_KEYWORDS,
    FLUTTER_KEYWORDS,
    FRONTEND_KEYWORDS,
    HIRING_KEYWORDS,
    HYBRID_KEYWORDS,
    MOBILE_KEYWORDS,
    ONSITE_KEYWORDS,
    REMOTE_KEYWORDS,
    SENIORITY_KEYWORDS,
)
from app.hiring_detection.types import HiringOpportunity

JOB_LINK_HINTS = (
    "job",
    "jobs",
    "career",
    "careers",
    "opening",
    "position",
    "role",
    "apply",
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "teamtailor",
    "breezy",
    "recruitee",
    "smartrecruiters",
    "workday",
)

LOCATION_PATTERN = re.compile(
    r"\b(remote|hybrid|on-?site|san francisco|new york|london|berlin|toronto|"
    r"austin|seattle|bangalore|bengaluru|singapore|amsterdam|paris|mumbai|"
    r"dublin|chicago|boston|los angeles|united states|india|germany|uk|usa)\b",
    re.IGNORECASE,
)


def match_keywords(text: str) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for keyword in sorted(HIRING_KEYWORDS, key=len, reverse=True):
        if keyword in lowered and keyword not in matched:
            matched.append(keyword)
    return matched


def detect_seniority(text: str) -> str | None:
    lowered = text.lower()
    for keyword in SENIORITY_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return keyword.title() if keyword != "mid-level" else "Mid"
    return None


def detect_work_mode(text: str) -> bool | None:
    lowered = text.lower()
    if any(token in lowered for token in REMOTE_KEYWORDS):
        return True
    if any(token in lowered for token in HYBRID_KEYWORDS):
        return False
    if any(token in lowered for token in ONSITE_KEYWORDS):
        return False
    return None


def detect_employment_type(text: str) -> str | None:
    lowered = text.lower()
    for label, keywords in EMPLOYMENT_TYPE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return None


def detect_location(text: str) -> str | None:
    match = LOCATION_PATTERN.search(text)
    if match:
        return match.group(0).strip().title()
    return None


def classify_job_categories(matched: list[str]) -> dict[str, bool]:
    lowered = {item.lower() for item in matched}
    return {
        "flutter": bool(lowered & FLUTTER_KEYWORDS),
        "mobile": bool(lowered & MOBILE_KEYWORDS),
        "frontend": bool(lowered & FRONTEND_KEYWORDS),
        "engineering": bool(lowered & ENGINEERING_KEYWORDS),
    }


def _confidence_for(matched: list[str], *, has_url: bool, provider: str | None) -> float:
    score = 0.35
    if matched:
        score += min(0.4, 0.08 * len(matched))
    if has_url:
        score += 0.1
    if provider:
        score += 0.15
    if any(keyword in FLUTTER_KEYWORDS for keyword in matched):
        score += 0.1
    return round(min(1.0, score), 2)


def extract_jobs_from_html(
    html: str,
    *,
    source_page: str,
    default_provider: str | None = None,
) -> list[HiringOpportunity]:
    soup = BeautifulSoup(html or "", "html.parser")
    opportunities: list[HiringOpportunity] = []
    opportunities.extend(
        _extract_from_anchors(soup, source_page=source_page, default_provider=default_provider)
    )
    opportunities.extend(
        _extract_from_structured(soup, source_page=source_page, default_provider=default_provider)
    )
    opportunities.extend(
        _extract_from_text_blocks(soup, source_page=source_page, default_provider=default_provider)
    )
    return _dedupe_opportunities(opportunities)


def _extract_from_anchors(
    soup: BeautifulSoup,
    *,
    source_page: str,
    default_provider: str | None,
) -> list[HiringOpportunity]:
    results: list[HiringOpportunity] = []
    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        title = " ".join(anchor.stripped_strings).strip()
        if not href or not title or len(title) < 4 or len(title) > 160:
            continue
        href_l = href.lower()
        title_l = title.lower()
        if not any(hint in href_l or hint in title_l for hint in JOB_LINK_HINTS):
            # Still accept if title itself contains hiring keywords.
            if not match_keywords(title):
                continue
        matched = match_keywords(f"{title} {href}")
        if not matched and not any(hint in href_l for hint in JOB_LINK_HINTS):
            continue
        # Skip pure navigation labels.
        if title_l in {"careers", "jobs", "join us", "openings", "hiring", "view all jobs"}:
            continue
        url = normalize_job_url(urljoin(source_page, href), source_page)
        provider = detect_ats_provider(url) or default_provider
        parent_text = ""
        parent = anchor.parent
        if isinstance(parent, Tag):
            parent_text = " ".join(parent.stripped_strings)[:300]
        blob = f"{title} {parent_text}"
        if not matched:
            matched = match_keywords(blob)
        results.append(
            HiringOpportunity(
                title=title,
                department=_guess_department(matched),
                location=detect_location(blob),
                remote=detect_work_mode(blob),
                employment_type=detect_employment_type(blob),
                url=url,
                provider=provider,
                confidence=_confidence_for(matched, has_url=True, provider=provider),
                matched_keywords=matched,
                seniority=detect_seniority(blob),
                source_page=source_page,
            )
        )
    return results


def _extract_from_structured(
    soup: BeautifulSoup,
    *,
    source_page: str,
    default_provider: str | None,
) -> list[HiringOpportunity]:
    results: list[HiringOpportunity] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = script.string or script.get_text()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        for item in _walk_jsonld(payload):
            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue
            description = str(item.get("description") or "")
            blob = f"{title} {description}"
            matched = match_keywords(blob)
            if not matched and "job" not in str(item.get("@type", "")).lower():
                continue
            job_url = item.get("url") or item.get("sameAs") or source_page
            if isinstance(job_url, list):
                job_url = job_url[0] if job_url else source_page
            url = normalize_job_url(str(job_url), source_page)
            provider = detect_ats_provider(url) or default_provider
            location = None
            job_location = item.get("jobLocation")
            if isinstance(job_location, dict):
                address = job_location.get("address")
                if isinstance(address, dict):
                    location = address.get("addressLocality") or address.get("name")
                else:
                    location = job_location.get("name")
            elif isinstance(job_location, str):
                location = job_location
            results.append(
                HiringOpportunity(
                    title=title,
                    department=_guess_department(matched),
                    location=location or detect_location(blob),
                    remote=detect_work_mode(blob),
                    employment_type=(
                        str(item.get("employmentType") or "").lower()
                        or detect_employment_type(blob)
                    ),
                    url=url,
                    provider=provider,
                    confidence=_confidence_for(matched, has_url=True, provider=provider),
                    matched_keywords=matched,
                    seniority=detect_seniority(blob),
                    source_page=source_page,
                )
            )
    return results


def _extract_from_text_blocks(
    soup: BeautifulSoup,
    *,
    source_page: str,
    default_provider: str | None,
) -> list[HiringOpportunity]:
    results: list[HiringOpportunity] = []
    for node in soup.find_all(["li", "article", "div", "tr"]):
        if not isinstance(node, Tag):
            continue
        text = " ".join(node.stripped_strings)
        if not text or len(text) > 280:
            continue
        matched = match_keywords(text)
        if not matched:
            continue
        # Prefer blocks that look like job rows.
        if not any(
            token in text.lower()
            for token in ("engineer", "developer", "flutter", "mobile", "frontend", "react")
        ):
            continue
        title = text.split("·")[0].split("|")[0].split("-")[0].strip()
        if len(title) < 4 or len(title) > 120:
            title = matched[0].title()
        href = None
        anchor = node.find("a", href=True)
        if isinstance(anchor, Tag):
            href = str(anchor.get("href"))
        url = normalize_job_url(urljoin(source_page, href), source_page) if href else source_page
        provider = detect_ats_provider(url) or default_provider
        results.append(
            HiringOpportunity(
                title=title,
                department=_guess_department(matched),
                location=detect_location(text),
                remote=detect_work_mode(text),
                employment_type=detect_employment_type(text),
                url=url,
                provider=provider,
                confidence=_confidence_for(matched, has_url=bool(href), provider=provider),
                matched_keywords=matched,
                seniority=detect_seniority(text),
                source_page=source_page,
            )
        )
    return results


def _guess_department(matched: list[str]) -> str | None:
    categories = classify_job_categories(matched)
    if categories["flutter"] or categories["mobile"]:
        return "Mobile Engineering"
    if categories["frontend"]:
        return "Frontend Engineering"
    if categories["engineering"]:
        return "Engineering"
    return None


def _walk_jsonld(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        type_value = payload.get("@type")
        types = (
            [str(type_value).lower()]
            if isinstance(type_value, str)
            else [str(item).lower() for item in type_value] if isinstance(type_value, list) else []
        )
        if any("jobposting" in item or item == "job" for item in types):
            items.append(payload)
        for value in payload.values():
            items.extend(_walk_jsonld(value))
    elif isinstance(payload, list):
        for item in payload:
            items.extend(_walk_jsonld(item))
    return items


def _dedupe_opportunities(opportunities: list[HiringOpportunity]) -> list[HiringOpportunity]:
    merged: dict[str, HiringOpportunity] = {}
    for opportunity in opportunities:
        key = (
            (opportunity.url or "").lower().rstrip("/"),
            opportunity.title.strip().lower(),
        )
        existing = merged.get(f"{key[0]}|{key[1]}")
        if existing is None:
            merged[f"{key[0]}|{key[1]}"] = opportunity
            continue
        # Keep higher confidence / richer keywords.
        if opportunity.confidence > existing.confidence or len(opportunity.matched_keywords) > len(
            existing.matched_keywords
        ):
            merged[f"{key[0]}|{key[1]}"] = opportunity
    return list(merged.values())


def host_hint(url: str) -> str:
    return urlparse(url).netloc.lower()
