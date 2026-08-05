"""Founder Enrichment — build founder profiles from contacts and page signals."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.company_intelligence.models import CompanyIntelligenceReport
from app.contact_discovery.types import (
    CompanyDecisionMaker,
    ContactCandidate,
    ContactDiscoveryReport,
)
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.founder_enrichment.models import FounderEnrichmentReport, FounderProfile

FOUNDER_ROLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "founder",
        "co-founder",
        "cofounder",
        "co founder",
        "ceo",
        "owner",
        "chief executive",
    }
)

LOCATION_PATTERN = re.compile(
    r"\b("
    r"san francisco|new york|london|berlin|toronto|austin|seattle|bangalore|"
    r"bengaluru|singapore|amsterdam|paris|mumbai|dublin|chicago|boston|"
    r"los angeles|united states|india|germany|uk|usa|remote"
    r")\b",
    re.IGNORECASE,
)

PERSONAL_SITE_HINTS = (
    "personal",
    "portfolio",
    "about-me",
    "me.",
    "blog.",
)

AVATAR_HINTS = ("avatar", "profile", "headshot", "portrait", "team", "founder", "photo")


class FounderEnrichmentService:
    """Enrich founder profiles from decision makers + contact discovery (+ optional CI)."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def enrich(
        self,
        *,
        contacts: ContactDiscoveryReport | None = None,
        website_profile: WebsiteProfile | None = None,
        company_intelligence: CompanyIntelligenceReport | None = None,
        decision_makers: list[CompanyDecisionMaker] | None = None,
    ) -> FounderEnrichmentReport:
        url = ""
        if contacts and contacts.url:
            url = contacts.url
        elif website_profile:
            url = website_profile.final_url or website_profile.url

        candidates = self._select_founders(
            contacts=contacts,
            decision_makers=decision_makers,
        )
        if not candidates:
            report = FounderEnrichmentReport(url=url, empty=True, confidence=0.0)
            self.logger.info(
                "url=%s founders_found=0 empty=true confidence=0.00",
                url,
            )
            return report

        html = ""
        if website_profile and website_profile.metadata:
            html = str(website_profile.metadata.get("html") or "")
        soup = BeautifulSoup(html, "html.parser") if html else None

        founders: list[FounderProfile] = []
        for candidate in candidates:
            profile = self._build_profile(
                candidate,
                soup=soup,
                base_url=url,
                company_intelligence=company_intelligence,
                contacts=contacts,
            )
            founders.append(profile)

        founders.sort(key=lambda item: (-item.confidence, (item.full_name or "").lower()))
        primary = founders[0] if founders else None
        confidence = primary.confidence if primary else 0.0

        report = FounderEnrichmentReport(
            url=url,
            founders_found=len(founders),
            founders=founders,
            primary_founder=primary,
            confidence=confidence,
            empty=False,
        )
        self.logger.info(
            ("url=%s founders_found=%d primary=%s role=%s " "email=%s linkedin=%s confidence=%.2f"),
            report.url,
            report.founders_found,
            primary.full_name if primary else None,
            primary.role if primary else None,
            bool(primary.email) if primary else False,
            bool(primary.linkedin) if primary else False,
            report.confidence,
        )
        return report

    def _select_founders(
        self,
        *,
        contacts: ContactDiscoveryReport | None,
        decision_makers: list[CompanyDecisionMaker] | None,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()

        makers = list(decision_makers or [])
        if contacts:
            makers.extend(contacts.decision_makers or [])

        for maker in makers:
            if not _is_founder_role(maker.role):
                continue
            key = _identity_key(
                name=maker.name,
                email=maker.email,
                linkedin=maker.linkedin,
            )
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                {
                    "full_name": maker.name,
                    "role": maker.role,
                    "email": maker.email,
                    "linkedin": maker.linkedin,
                    "github": maker.github,
                    "twitter": maker.twitter,
                    "confidence": maker.confidence,
                    "contact_score": maker.contact_score,
                    "source_page": maker.source_page,
                    "discovery_source": maker.discovery_source,
                    "first_name": None,
                    "last_name": None,
                }
            )

        if contacts:
            for contact in contacts.contacts or []:
                role = contact.role or contact.company_role
                if not _is_founder_role(role):
                    continue
                name = contact.display_name or contact.full_name
                key = _identity_key(name=name, email=contact.email, linkedin=contact.linkedin)
                if key in seen:
                    # Merge richer fields into existing.
                    self._merge_into(selected, key, contact)
                    continue
                seen.add(key)
                selected.append(
                    {
                        "full_name": name,
                        "first_name": contact.first_name,
                        "last_name": contact.last_name,
                        "role": role,
                        "email": contact.email,
                        "linkedin": contact.linkedin,
                        "github": contact.github,
                        "twitter": contact.twitter,
                        "confidence": contact.confidence,
                        "contact_score": contact.contact_score,
                        "source_page": contact.source_page,
                        "discovery_source": contact.discovery_source,
                    }
                )

        # Prefer best contact when it is a founder and not already included.
        if contacts and contacts.best_contact:
            best = contacts.best_contact
            role = best.role or best.company_role
            if _is_founder_role(role):
                name = best.display_name or best.full_name
                key = _identity_key(name=name, email=best.email, linkedin=best.linkedin)
                if key not in seen:
                    selected.append(
                        {
                            "full_name": name,
                            "first_name": best.first_name,
                            "last_name": best.last_name,
                            "role": role,
                            "email": best.email,
                            "linkedin": best.linkedin,
                            "github": best.github,
                            "twitter": best.twitter,
                            "confidence": best.confidence,
                            "contact_score": best.contact_score,
                            "source_page": best.source_page,
                            "discovery_source": best.discovery_source,
                        }
                    )

        return selected

    @staticmethod
    def _merge_into(selected: list[dict[str, Any]], key: str, contact: ContactCandidate) -> None:
        for item in selected:
            item_key = _identity_key(
                name=item.get("full_name"),
                email=item.get("email"),
                linkedin=item.get("linkedin"),
            )
            if item_key != key:
                continue
            item["email"] = item.get("email") or contact.email
            item["linkedin"] = item.get("linkedin") or contact.linkedin
            item["github"] = item.get("github") or contact.github
            item["twitter"] = item.get("twitter") or contact.twitter
            item["first_name"] = item.get("first_name") or contact.first_name
            item["last_name"] = item.get("last_name") or contact.last_name
            item["role"] = item.get("role") or contact.role or contact.company_role
            item["confidence"] = max(float(item.get("confidence") or 0), contact.confidence)
            break

    def _build_profile(
        self,
        candidate: dict[str, Any],
        *,
        soup: BeautifulSoup | None,
        base_url: str,
        company_intelligence: CompanyIntelligenceReport | None,
        contacts: ContactDiscoveryReport | None,
    ) -> FounderProfile:
        full_name = (candidate.get("full_name") or "").strip() or None
        first_name = candidate.get("first_name")
        last_name = candidate.get("last_name")
        if full_name and (not first_name or not last_name):
            parts = full_name.split()
            if len(parts) >= 2:
                first_name = first_name or parts[0]
                last_name = last_name or parts[-1]
            elif len(parts) == 1:
                first_name = first_name or parts[0]

        linkedin = candidate.get("linkedin") or _single_social(
            contacts.linkedin_profiles if contacts else [], kind="linkedin"
        )
        github = candidate.get("github") or _single_social(
            contacts.github_profiles if contacts else [], kind="github"
        )
        twitter = candidate.get("twitter") or _single_social(
            contacts.twitter_profiles if contacts else [], kind="twitter"
        )

        bio = None
        avatar_url = None
        personal_website = None
        location = None
        if soup is not None and full_name:
            bio = _extract_bio(soup, full_name)
            avatar_url = _extract_avatar(soup, full_name, base_url)
            personal_website = _extract_personal_website(soup, full_name, base_url)
            location = _extract_location_near_name(soup, full_name)

        if location is None and company_intelligence:
            # Soft fallback from company keywords / industry text — not headquarters.
            for keyword in company_intelligence.keywords:
                match = LOCATION_PATTERN.search(keyword)
                if match:
                    location = match.group(0).title()
                    break

        confidence = _confidence_for(
            full_name=full_name,
            role=candidate.get("role"),
            email=candidate.get("email"),
            linkedin=linkedin,
            github=github,
            twitter=twitter,
            bio=bio,
            avatar_url=avatar_url,
            base_confidence=float(candidate.get("confidence") or 0),
            contact_score=int(candidate.get("contact_score") or 0),
        )

        return FounderProfile(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            role=candidate.get("role"),
            email=(candidate.get("email") or None),
            bio=bio,
            github=github,
            twitter=twitter,
            linkedin=linkedin,
            personal_website=personal_website,
            location=location,
            avatar_url=avatar_url,
            confidence=confidence,
            source_page=candidate.get("source_page"),
            discovery_source=candidate.get("discovery_source"),
        )


def _is_founder_role(role: str | None) -> bool:
    if not role:
        return False
    lowered = role.strip().lower()
    if lowered in FOUNDER_ROLE_KEYWORDS:
        return True
    return any(token in lowered for token in FOUNDER_ROLE_KEYWORDS)


def _identity_key(*, name: str | None, email: str | None, linkedin: str | None) -> str:
    if email:
        return f"email:{(email or '').strip().lower()}"
    if linkedin:
        return f"linkedin:{(linkedin or '').rstrip('/').lower()}"
    return f"name:{(name or '').strip().lower()}"


def _single_social(links: list[str], *, kind: str) -> str | None:
    """Use a report-level social URL only when there is exactly one plausible person link."""
    filtered: list[str] = []
    for link in links:
        lowered = link.lower()
        if kind == "linkedin":
            if "linkedin.com/in/" in lowered:
                filtered.append(link)
        elif kind == "github":
            if "github.com/" not in lowered:
                continue
            path = [p for p in urlparse(link).path.split("/") if p]
            if len(path) == 1 and path[0].lower() not in {"features", "pricing", "about"}:
                filtered.append(link)
        elif kind == "twitter":
            if "twitter.com/" in lowered or "x.com/" in lowered:
                filtered.append(link)
    if len(filtered) == 1:
        return filtered[0]
    return None


def _extract_bio(soup: BeautifulSoup, full_name: str) -> str | None:
    name_lower = full_name.lower()
    for node in soup.find_all(["p", "div", "li", "article", "section"]):
        if not isinstance(node, Tag):
            continue
        text = " ".join(node.stripped_strings)
        if not text or full_name.split()[0].lower() not in text.lower():
            continue
        if name_lower not in text.lower() and not any(
            part.lower() in text.lower() for part in full_name.split() if len(part) > 2
        ):
            continue
        if 40 <= len(text) <= 600:
            # Prefer bios that mention founder-ish context.
            return text[:500]
    return None


def _extract_avatar(soup: BeautifulSoup, full_name: str, base_url: str) -> str | None:
    first = full_name.split()[0].lower() if full_name else ""
    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = str(img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        blob = " ".join(
            [
                src,
                str(img.get("alt") or ""),
                str(img.get("class") or ""),
                str(img.get("id") or ""),
            ]
        ).lower()
        if first and first in blob:
            return urljoin(base_url, src)
        if (
            any(hint in blob for hint in AVATAR_HINTS)
            and first
            and first in (str(img.get("alt") or "").lower())
        ):
            return urljoin(base_url, src)
    return None


def _extract_personal_website(soup: BeautifulSoup, full_name: str, base_url: str) -> str | None:
    first = full_name.split()[0].lower() if full_name else ""
    base_host = urlparse(base_url).netloc.lower()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "").strip()
        text = " ".join(anchor.stripped_strings).lower()
        if not href.startswith(("http://", "https://")):
            continue
        host = urlparse(href).netloc.lower()
        if host == base_host or host.endswith(f".{base_host}"):
            continue
        if any(
            social in host for social in ("linkedin.", "twitter.", "x.com", "github.", "facebook.")
        ):
            continue
        if first and (first in text or first in host):
            return href
        if any(hint in text or hint in href.lower() for hint in PERSONAL_SITE_HINTS):
            if first and first in f"{text} {href.lower()}":
                return href
    return None


def _extract_location_near_name(soup: BeautifulSoup, full_name: str) -> str | None:
    first = full_name.split()[0].lower() if full_name else ""
    for node in soup.find_all(["p", "div", "li", "span"]):
        if not isinstance(node, Tag):
            continue
        text = " ".join(node.stripped_strings)
        if not text or (first and first not in text.lower()):
            continue
        match = LOCATION_PATTERN.search(text)
        if match:
            return match.group(0).title()
    return None


def _confidence_for(
    *,
    full_name: str | None,
    role: str | None,
    email: str | None,
    linkedin: str | None,
    github: str | None,
    twitter: str | None,
    bio: str | None,
    avatar_url: str | None,
    base_confidence: float,
    contact_score: int,
) -> float:
    score = max(0.15, min(0.5, base_confidence)) if base_confidence else 0.15
    if contact_score:
        score = max(score, min(0.7, contact_score / 100))
    if full_name:
        score += 0.1
    if _is_founder_role(role):
        score += 0.15
    if email:
        score += 0.15
    if linkedin:
        score += 0.1
    if github or twitter:
        score += 0.05
    if bio:
        score += 0.05
    if avatar_url:
        score += 0.05
    return round(min(1.0, score), 2)
