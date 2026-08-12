from __future__ import annotations

import re

from app.contact_discovery.ranking import (
    DECISION_MAKER_ROLE_NAMES,
    DEFAULT_CONTACT_RANKING,
    FAKE_CONTACT_LABELS,
    FAKE_EMAIL_DOMAIN_LABELS,
    FAKE_EMAIL_DOMAINS,
    NAME_CONNECTIVE_TOKENS,
    NON_PERSON_NAME_TOKENS,
    REJECTED_EMAIL_LOCAL_PARTS,
    SUSPICIOUS_EMAIL_TLDS,
    ContactRankingConfig,
)

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|@| at )\s*([a-zA-Z0-9.\-]+)\s*"
    r"(?:\[dot\]|\(dot\)|\.| dot )\s*([a-zA-Z]{2,})",
    re.IGNORECASE,
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}

GENERIC_LOCAL_PARTS = {
    "support",
    "hello",
    "contact",
    "info",
    "careers",
    "jobs",
    "hr",
    "sales",
    "marketing",
    "team",
    "admin",
}

# Generic inboxes look real but often bounce or go to shared boxes — skip for cold outbound.
OUTBOUND_SKIP_LOCAL_PARTS: frozenset[str] = frozenset(
    GENERIC_LOCAL_PARTS
    | {
        "hi",
        "hey",
        "mail",
        "office",
        "help",
        "enquiries",
        "enquiry",
        "inquiries",
        "inquiry",
        "press",
        "media",
        "lists",
        "list",
        "newsletter",
        "billing",
        "orders",
        "order",
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
    }
)
HIGH_VALUE_LOCAL_PARTS = {"founder", "ceo", "cto", "owner", "hiring"}

SUPPORTED_ROLES = (
    "Co-Founder",
    "Founder",
    "CEO",
    "CTO",
    "VP Engineering",
    "Engineering Manager",
    "Product Manager",
    "Hiring Manager",
    "Mobile Lead",
    "Owner",
    "Director",
    "Software Engineer",
    "Developer",
    "Marketing",
    "Sales",
    "Support",
    "Recruiter",
    "HR",
)

ROLE_ALIASES = {
    "co-founder": "Co-Founder",
    "cofounder": "Co-Founder",
    "founder": "Founder",
    "chief executive officer": "CEO",
    "ceo": "CEO",
    "chief technology officer": "CTO",
    "cto": "CTO",
    "vp engineering": "VP Engineering",
    "vice president of engineering": "VP Engineering",
    "vice president engineering": "VP Engineering",
    "head of engineering": "VP Engineering",
    "engineering manager": "Engineering Manager",
    "eng manager": "Engineering Manager",
    "product manager": "Product Manager",
    "hiring manager": "Hiring Manager",
    "mobile lead": "Mobile Lead",
    "head of mobile": "Mobile Lead",
    "owner": "Owner",
    "director": "Director",
    "software engineer": "Software Engineer",
    "developer": "Developer",
    "marketing": "Marketing",
    "sales": "Sales",
    "support": "Support",
    "recruiter": "Recruiter",
    "hr": "HR",
    "human resources": "HR",
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_image_filename(value: str) -> bool:
    lowered = value.lower().strip()
    return any(lowered.endswith(ext) for ext in IMAGE_EXTENSIONS)


def is_javascript_link(value: str) -> bool:
    return value.strip().lower().startswith("javascript:")


def is_fake_email(email: str) -> bool:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return True
    local_part, domain = normalized.rsplit("@", 1)
    if domain in FAKE_EMAIL_DOMAINS or domain.endswith(".localhost"):
        return True
    if local_part in REJECTED_EMAIL_LOCAL_PARTS:
        return True
    if local_part.startswith(("noreply", "no-reply", "donotreply")):
        return True
    if "privacy" in local_part:
        return True
    if is_image_filename(normalized):
        return True
    if "localhost" in domain:
        return True

    labels = [part for part in domain.split(".") if part]
    if len(labels) < 2:
        return True
    tld = labels[-1]
    if tld in SUSPICIOUS_EMAIL_TLDS:
        return True
    # Placeholder / CDN labels in any non-TLD segment (keeps acme.example fixtures valid).
    if any(label in FAKE_EMAIL_DOMAIN_LABELS for label in labels[:-1]):
        return True
    if any("cloudflare" in label for label in labels):
        return True
    return False


def is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    if is_javascript_link(email):
        return False
    if is_fake_email(email):
        return False
    if not EMAIL_PATTERN.fullmatch(email.strip()):
        return False
    return True


def is_generic_inbox_email(email: str | None) -> bool:
    """True for shared inboxes (hello@, info@, …) that frequently bounce on cold send."""
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].strip().lower()
    local = local.split("+", 1)[0]
    return local in OUTBOUND_SKIP_LOCAL_PARTS


def is_outbound_safe_email(email: str | None) -> bool:
    """Format-valid and not a generic/shared inbox."""
    if not email or not is_valid_email(email):
        return False
    return not is_generic_inbox_email(email)


def is_fake_contact_name(name: str | None) -> bool:
    if not name or not name.strip():
        return False
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    if cleaned in FAKE_CONTACT_LABELS:
        return True
    single_token_rejects = {
        "terms",
        "privacy",
        "pricing",
        "docs",
        "documentation",
        "marketplace",
        "blog",
        "login",
        "home",
        "menu",
        "cookies",
        "cookie",
        "subscribe",
        "newsletter",
        "navigation",
        "policy",
        "support",
        "info",
        "contact",
        "hello",
        "sign",
        "in",
        "up",
        "hi",
        "hey",
        "there",
        "team",
        "beta",
        "tester",
        "testers",
    }
    tokens = cleaned.replace("-", " ").split()
    if not tokens:
        return True
    if cleaned in single_token_rejects:
        return True
    # Reject greeting-prefixed scrapes ("hi priya", "hello team").
    if tokens[0] in {"hi", "hello", "hey", "dear"}:
        return True
    # Reject nav-like phrases ("Support Info Privacy", "Sign In", …).
    if any(
        token in {"privacy", "pricing", "terms", "policy", "cookie", "cookies"} for token in tokens
    ):
        return True
    if all(token in single_token_rejects for token in tokens):
        return True
    # Reject product/UI phrases ("Custom For", "Account Wallets", "Cloud Connector").
    if any(token in NAME_CONNECTIVE_TOKENS for token in tokens):
        return True
    non_person_hits = sum(1 for token in tokens if token in NON_PERSON_NAME_TOKENS)
    if non_person_hits == len(tokens):
        return True
    if len(tokens) >= 2 and non_person_hits >= (len(tokens) + 1) // 2:
        return True
    return False


_GREETING_PREFIX_RE = re.compile(r"^(hi|hello|hey|dear)\s+", re.IGNORECASE)


def normalize_person_name(name: str | None) -> str | None:
    """Return a usable person name, or None if the scrape is junk/greeting noise."""
    if not name or not name.strip():
        return None
    cleaned = re.sub(r"\s+", " ", name.strip())
    cleaned = _GREETING_PREFIX_RE.sub("", cleaned).strip(" ,.-")
    if not cleaned or is_fake_contact_name(cleaned):
        return None
    # Prefer first name only for email greetings when we have 2+ tokens.
    parts = cleaned.split()
    if len(parts) >= 2 and all(part[:1].isupper() for part in parts if part):
        return parts[0]
    return cleaned


def is_generic_email_contact(*, email: str | None, role: str | None, full_name: str | None) -> bool:
    if full_name and not is_fake_contact_name(full_name):
        role_l = (role or "").lower()
        if role_l in DECISION_MAKER_ROLE_NAMES:
            return False
        if role_l and role_l not in {part.lower() for part in GENERIC_LOCAL_PARTS}:
            return False
    if not email:
        return not bool(full_name)
    local = email.split("@", 1)[0].lower()
    return local in GENERIC_LOCAL_PARTS or local in {"hello", "info", "support", "contact"}


def is_decision_maker_role(role: str | None) -> bool:
    if not role:
        return False
    return role.strip().lower() in DECISION_MAKER_ROLE_NAMES


def split_name(full_name: str) -> tuple[str | None, str | None]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def normalize_role(raw_role: str | None) -> str | None:
    if not raw_role:
        return None
    cleaned = re.sub(r"\s+", " ", raw_role.strip())
    alias = ROLE_ALIASES.get(cleaned.lower())
    if alias:
        return alias
    for role in SUPPORTED_ROLES:
        if role.lower() in cleaned.lower():
            return role
    return cleaned.title()


def rank_contact(
    *,
    email: str | None,
    role: str | None,
    linkedin: str | None,
    github: str | None = None,
    full_name: str | None = None,
    config: ContactRankingConfig | None = None,
) -> tuple[int, int, float]:
    """Return (contact_score 0-100, contact_priority, confidence 0-1)."""
    cfg = config or DEFAULT_CONTACT_RANKING
    role_normalized = (role or "").strip()
    role_key = role_normalized.lower()
    local_part = email.split("@", 1)[0].lower() if email else ""

    score = cfg.generic_score
    priority = 99

    for entry in cfg.role_scores:
        if entry.role.lower() == role_key:
            score = entry.score
            priority = entry.priority
            break
    else:
        if local_part in cfg.generic_email_scores:
            score = cfg.generic_email_scores[local_part]
            if local_part in HIGH_VALUE_LOCAL_PARTS:
                priority = 3
            elif local_part in GENERIC_LOCAL_PARTS:
                priority = 10
        elif full_name:
            score = cfg.named_contact_score
            priority = 9
        elif linkedin or github:
            score = cfg.social_only_score
            priority = 11

    # Small boosts for richer identity without exceeding max.
    if email and (linkedin or github) and score < cfg.max_score:
        score = min(cfg.max_score, score + 3)
    if full_name and email and score < cfg.max_score:
        score = min(cfg.max_score, score + 2)

    score = max(cfg.min_score, min(cfg.max_score, score))
    confidence = round(score / 100.0, 2)
    return score, priority, confidence


def score_contact(
    *,
    email: str | None,
    role: str | None,
    linkedin: str | None,
    github: str | None = None,
    full_name: str | None = None,
) -> float:
    """Backward-compatible confidence score (0-1)."""
    _, _, confidence = rank_contact(
        email=email,
        role=role,
        linkedin=linkedin,
        github=github,
        full_name=full_name,
    )
    return confidence
