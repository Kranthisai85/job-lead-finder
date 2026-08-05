from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.contact_discovery.types import ContactCandidate, DiscoverySource
from app.contact_discovery.validators import (
    EMAIL_PATTERN,
    GENERIC_LOCAL_PARTS,
    OBFUSCATED_EMAIL_PATTERN,
    ROLE_ALIASES,
    SUPPORTED_ROLES,
    is_fake_contact_name,
    is_valid_email,
    normalize_email,
    normalize_role,
    rank_contact,
    split_name,
)

NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
PERSON_LINKEDIN_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+/?",
    re.IGNORECASE,
)
COMPANY_LINKEDIN_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9\-_%]+/?",
    re.IGNORECASE,
)
TWITTER_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/?",
    re.IGNORECASE,
)
GITHUB_USER_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.\-]+)/?",
    re.IGNORECASE,
)
GITHUB_SKIP_USERS = {
    "topics",
    "features",
    "pricing",
    "marketplace",
    "login",
    "join",
    "settings",
    "orgs",
    "organizations",
    "sponsors",
    "about",
    "events",
    "collections",
    "trending",
    "pulls",
    "issues",
    "notifications",
    "explore",
}


def extract_emails_from_text(text: str) -> list[str]:
    emails = {normalize_email(match) for match in EMAIL_PATTERN.findall(text)}
    for match in OBFUSCATED_EMAIL_PATTERN.finditer(text):
        rebuilt = f"{match.group(1)}@{match.group(2)}.{match.group(3)}"
        emails.add(normalize_email(rebuilt))
    return sorted(email for email in emails if is_valid_email(email))


def extract_mailto_emails(soup: BeautifulSoup) -> list[str]:
    emails: set[str] = set()
    for anchor in soup.select('a[href^="mailto:"]'):
        href = str(anchor.get("href", ""))
        address = href.replace("mailto:", "").split("?")[0].strip()
        if address:
            emails.add(normalize_email(address))
    return sorted(email for email in emails if is_valid_email(email))


def extract_github_profiles(text: str, links: list[str]) -> list[str]:
    blob = "\n".join([text, *links])
    profiles: set[str] = set()
    for match in GITHUB_USER_PATTERN.finditer(blob):
        url = match.group(0).rstrip("/")
        user = match.group(1).lower()
        path = urlparse(url).path.strip("/")
        parts = [part for part in path.split("/") if part]
        # Skip repository URLs (user/repo) and platform pages.
        if len(parts) != 1:
            continue
        if user in GITHUB_SKIP_USERS:
            continue
        profiles.add(url)
    return sorted(profiles)


def extract_social_profiles(text: str, links: list[str]) -> dict[str, list[str]]:
    blob = "\n".join([text, *links])
    linkedin_people = sorted(set(PERSON_LINKEDIN_PATTERN.findall(blob)))
    linkedin_companies = sorted(set(COMPANY_LINKEDIN_PATTERN.findall(blob)))
    twitter = sorted(
        {
            link
            for link in TWITTER_PATTERN.findall(blob)
            if not any(skip in link.lower() for skip in ("/intent/", "/share", "/home"))
        }
    )
    github = extract_github_profiles(text, links)
    return {
        "linkedin_profiles": linkedin_people,
        "linkedin_companies": linkedin_companies,
        "twitter_profiles": twitter,
        "github_profiles": github,
    }


def _detect_role_near_text(text: str) -> str | None:
    lowered = text.lower()
    # Prefer longer aliases first.
    for alias, role in sorted(ROLE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in lowered:
            return role
    for role in SUPPORTED_ROLES:
        if role.lower() in lowered:
            return role
    return None


def _pick_best_email(emails: list[str], full_name: str | None) -> str | None:
    if not emails:
        return None
    unique = list(dict.fromkeys(emails))
    if len(unique) == 1:
        return unique[0]

    non_generic = [
        email for email in unique if email.split("@", 1)[0].lower() not in GENERIC_LOCAL_PARTS
    ]
    pool = non_generic or unique
    if full_name:
        first = full_name.split()[0].lower()
        for email in pool:
            local = email.split("@", 1)[0].lower()
            if local.startswith(first[: max(3, min(len(first), 4))]):
                return email
    return pool[0]


def _build_candidate(
    *,
    full_name: str | None,
    email: str | None,
    role: str | None,
    linkedin: str | None,
    github: str | None,
    twitter: str | None,
    source_page: str | None,
    discovery_source: str,
) -> ContactCandidate | None:
    if full_name and is_fake_contact_name(full_name):
        return None
    if email and not is_valid_email(email):
        email = None
    if not any([full_name, email, linkedin, github]):
        return None

    normalized_role = normalize_role(role)
    score, priority, confidence = rank_contact(
        email=email,
        role=normalized_role,
        linkedin=linkedin,
        github=github,
        full_name=full_name,
    )
    first_name, last_name = split_name(full_name) if full_name else (None, None)
    return ContactCandidate(
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        email=email,
        role=normalized_role,
        company_role=normalized_role,
        linkedin=linkedin,
        github=github,
        twitter=twitter,
        source_page=source_page,
        discovery_source=discovery_source,
        contact_score=score,
        contact_priority=priority,
        confidence=confidence,
    )


def extract_people_from_html(
    soup: BeautifulSoup,
    source_page: str | None,
    *,
    discovery_source: str = DiscoverySource.HTML.value,
) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    text_blocks: list[str] = []

    for selector in ("section", "article", "div", "li", "footer", "p", "header"):
        for node in soup.find_all(selector):
            if not isinstance(node, Tag):
                continue
            # Skip obvious navigation chrome.
            classes = " ".join(node.get("class", [])).lower() if node.get("class") else ""
            node_id = str(node.get("id", "")).lower()
            if any(
                token in classes or token in node_id
                for token in ("nav", "menu", "cookie", "footer-links", "breadcrumb")
            ):
                continue
            text = " ".join(node.stripped_strings)
            if not text or len(text) > 500:
                continue
            text_blocks.append(text)

    for text in text_blocks:
        role = _detect_role_near_text(text)
        if not role:
            continue
        names = [name for name in NAME_PATTERN.findall(text) if not is_fake_contact_name(name)]
        emails = extract_emails_from_text(text)
        linkedin_matches = PERSON_LINKEDIN_PATTERN.findall(text)
        twitter_matches = TWITTER_PATTERN.findall(text)
        github_matches = extract_github_profiles(text, [])

        if not names and not emails and not linkedin_matches:
            continue

        candidate = _build_candidate(
            full_name=names[0] if names else None,
            email=_pick_best_email(emails, names[0] if names else None),
            role=role,
            linkedin=linkedin_matches[0] if linkedin_matches else None,
            github=github_matches[0] if github_matches else None,
            twitter=twitter_matches[0] if twitter_matches else None,
            source_page=source_page,
            discovery_source=discovery_source,
        )
        if candidate is not None:
            candidates.append(candidate)

    return candidates


def extract_json_ld_people(
    soup: BeautifulSoup,
    source_page: str | None,
) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = script.string or script.get_text()
        if not content:
            continue
        lowered = content.lower()
        if '"person"' not in lowered and '"employee"' not in lowered:
            continue

        names = [name for name in NAME_PATTERN.findall(content) if not is_fake_contact_name(name)]
        emails = extract_emails_from_text(content)
        role = _detect_role_near_text(content)
        linkedin_matches = PERSON_LINKEDIN_PATTERN.findall(content)
        github_matches = extract_github_profiles(content, [])

        if not names and not emails:
            continue

        candidate = _build_candidate(
            full_name=names[0] if names else None,
            email=emails[0] if emails else None,
            role=role,
            linkedin=linkedin_matches[0] if linkedin_matches else None,
            github=github_matches[0] if github_matches else None,
            twitter=None,
            source_page=source_page,
            discovery_source=DiscoverySource.JSON_LD.value,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def extract_generic_email_contacts(
    emails: list[str],
    source_page: str | None,
) -> list[ContactCandidate]:
    contacts: list[ContactCandidate] = []
    for email in emails:
        if not is_valid_email(email):
            continue
        local_part = email.split("@", 1)[0]
        role = None
        if local_part in {"founder", "ceo", "cto", "hiring"}:
            role = normalize_role(local_part)
        elif local_part in {"support", "careers", "jobs", "hr", "sales", "marketing"}:
            role = normalize_role(local_part)
        candidate = _build_candidate(
            full_name=None,
            email=email,
            role=role,
            linkedin=None,
            github=None,
            twitter=None,
            source_page=source_page,
            discovery_source=DiscoverySource.EMAIL.value,
        )
        if candidate is not None:
            contacts.append(candidate)
    return contacts


def is_person_linkedin(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.startswith("/in/")
