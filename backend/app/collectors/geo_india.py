"""Detect and prioritize Indian startup signals in collected leads."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.collectors.types import CompanyLead

_INDIA_LOCATION_RE = re.compile(
    r"\b("
    r"india|indian|bharat|"
    r"bangalore|bengaluru|mumbai|delhi|new\s*delhi|hyderabad|chennai|pune|"
    r"kolkata|gurgaon|gurugram|noida|ahmedabad|jaipur|kochi|trivandrum|"
    r"thiruvananthapuram|indore|chandigarh|coimbatore|surat|"
    r"karnataka|maharashtra|tamil\s*nadu|telangana|kerala|gujarat"
    r")\b",
    re.IGNORECASE,
)

_INDIA_TLDS = frozenset({".in", ".co.in", ".org.in", ".net.in", ".firm.in", ".gen.in"})


def website_looks_indian(website: str | None) -> bool:
    host = (urlparse(website or "").hostname or "").lower()
    if not host:
        return False
    return any(host.endswith(tld) for tld in _INDIA_TLDS)


def text_mentions_india(*parts: Any) -> bool:
    blob = " ".join(str(part or "") for part in parts)
    return bool(_INDIA_LOCATION_RE.search(blob))


def india_match_score(
    *,
    website: str = "",
    locations: str = "",
    regions: list[str] | None = None,
    description: str = "",
    name: str = "",
    extra: str = "",
) -> int:
    """Higher = stronger India signal. Used for sorting, not hard filtering."""
    score = 0
    region_blob = " ".join(regions or [])
    if website_looks_indian(website):
        score += 40
    if text_mentions_india(locations, region_blob):
        score += 50
    if text_mentions_india(description, name, extra):
        score += 20
    return score


def prioritize_india_leads(leads: list[CompanyLead]) -> list[CompanyLead]:
    """Stable sort: Indian leads first, then everyone else (original order preserved)."""

    def _key(lead: CompanyLead) -> tuple[int, int]:
        meta = lead.metadata or {}
        score = int(meta.get("india_score") or 0)
        if score <= 0:
            score = india_match_score(
                website=lead.website,
                locations=str(meta.get("all_locations") or meta.get("locations") or ""),
                regions=list(meta.get("regions") or []),
                description=lead.description or "",
                name=lead.name,
                extra=" ".join(lead.tags or []),
            )
        # Negative so higher india scores come first; index preserved via stable sort.
        return (-score, 0)

    return sorted(leads, key=_key)
