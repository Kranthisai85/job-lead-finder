import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.contact_discovery.types import ContactCandidate
from app.contact_discovery.validators import (
    EMAIL_PATTERN,
    OBFUSCATED_EMAIL_PATTERN,
    ROLE_ALIASES,
    SUPPORTED_ROLES,
    is_valid_email,
    normalize_email,
    normalize_role,
    score_contact,
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
GITHUB_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.\-]+/?",
    re.IGNORECASE,
)


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
    github = sorted(
        {
            link
            for link in GITHUB_PATTERN.findall(blob)
            if not any(skip in link.lower() for skip in ("/topics/", "/features", "/login"))
        }
    )
    return {
        "linkedin_profiles": linkedin_people,
        "linkedin_companies": linkedin_companies,
        "twitter_profiles": twitter,
        "github_profiles": github,
    }


def _detect_role_near_text(text: str) -> str | None:
    lowered = text.lower()
    for alias, role in ROLE_ALIASES.items():
        if alias in lowered:
            return role
    for role in SUPPORTED_ROLES:
        if role.lower() in lowered:
            return role
    return None


def extract_people_from_html(
    soup: BeautifulSoup, source_page: str | None
) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    text_blocks: list[str] = []

    for selector in ("section", "article", "div", "li", "footer", "p"):
        for node in soup.find_all(selector):
            if not isinstance(node, Tag):
                continue
            text = " ".join(node.stripped_strings)
            if not text or len(text) > 400:
                continue
            text_blocks.append(text)

    for text in text_blocks:
        role = _detect_role_near_text(text)
        if not role:
            continue
        names = NAME_PATTERN.findall(text)
        emails = extract_emails_from_text(text)
        linkedin_matches = PERSON_LINKEDIN_PATTERN.findall(text)
        twitter_matches = TWITTER_PATTERN.findall(text)

        if not names and not emails and not linkedin_matches:
            continue

        full_name = names[0] if names else None
        first_name, last_name = split_name(full_name) if full_name else (None, None)
        email = emails[0] if emails else None
        linkedin = linkedin_matches[0] if linkedin_matches else None
        twitter = twitter_matches[0] if twitter_matches else None

        candidates.append(
            ContactCandidate(
                full_name=full_name,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=normalize_role(role),
                linkedin=linkedin,
                twitter=twitter,
                source_page=source_page,
                confidence=score_contact(email=email, role=role, linkedin=linkedin),
            )
        )

    return candidates


def extract_json_ld_people(soup: BeautifulSoup, source_page: str | None) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = script.string or script.get_text()
        if not content:
            continue
        lowered = content.lower()
        if '"person"' not in lowered and '"employee"' not in lowered:
            continue

        names = NAME_PATTERN.findall(content)
        emails = extract_emails_from_text(content)
        role = _detect_role_near_text(content)
        linkedin_matches = PERSON_LINKEDIN_PATTERN.findall(content)

        if not names and not emails:
            continue

        full_name = names[0] if names else None
        first_name, last_name = split_name(full_name) if full_name else (None, None)
        email = emails[0] if emails else None
        linkedin = linkedin_matches[0] if linkedin_matches else None
        candidates.append(
            ContactCandidate(
                full_name=full_name,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=normalize_role(role),
                linkedin=linkedin,
                source_page=source_page,
                confidence=score_contact(email=email, role=role, linkedin=linkedin),
            )
        )
    return candidates


def extract_generic_email_contacts(
    emails: list[str],
    source_page: str | None,
) -> list[ContactCandidate]:
    contacts: list[ContactCandidate] = []
    for email in emails:
        local_part = email.split("@", 1)[0]
        role = None
        if local_part in {"founder", "ceo", "cto"}:
            role = normalize_role(local_part)
        elif local_part in {"support", "careers", "jobs", "hr", "sales", "marketing"}:
            role = normalize_role(local_part)
        contacts.append(
            ContactCandidate(
                email=email,
                role=role,
                source_page=source_page,
                confidence=score_contact(email=email, role=role, linkedin=None),
            )
        )
    return contacts


def is_person_linkedin(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.startswith("/in/")
