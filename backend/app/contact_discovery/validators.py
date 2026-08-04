import re

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|@| at )\s*([a-zA-Z0-9.\-]+)\s*"
    r"(?:\[dot\]|\(dot\)|\.| dot )\s*([a-zA-Z]{2,})",
    re.IGNORECASE,
)
FAKE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "test.com",
    "domain.com",
    "email.com",
    "yourdomain.com",
    "company.com",
    "sentry.io",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
IGNORED_LOCAL_PARTS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "privacy",
    "unsubscribe",
    "mailer-daemon",
    "postmaster",
}
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
HIGH_VALUE_LOCAL_PARTS = {"founder", "ceo", "cto", "owner"}

SUPPORTED_ROLES = (
    "Co-Founder",
    "Founder",
    "CEO",
    "CTO",
    "Owner",
    "Director",
    "Engineering Manager",
    "Product Manager",
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
    "owner": "Owner",
    "director": "Director",
    "engineering manager": "Engineering Manager",
    "product manager": "Product Manager",
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
    if domain in FAKE_EMAIL_DOMAINS:
        return True
    if local_part in IGNORED_LOCAL_PARTS:
        return True
    if "privacy" in local_part:
        return True
    if is_image_filename(normalized):
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


def score_contact(
    *,
    email: str | None,
    role: str | None,
    linkedin: str | None,
) -> float:
    role_normalized = (role or "").lower()
    local_part = email.split("@", 1)[0].lower() if email else ""

    if role_normalized in {"ceo", "founder", "co-founder"} and email:
        return 0.95
    if role_normalized in {"ceo", "founder", "co-founder"} and linkedin:
        return 0.9
    if local_part in HIGH_VALUE_LOCAL_PARTS:
        return 0.85
    if role_normalized in {"cto", "owner", "director"} and (email or linkedin):
        return 0.8
    if local_part == "support":
        return 0.55
    if local_part in GENERIC_LOCAL_PARTS:
        return 0.35
    if email and linkedin:
        return 0.7
    if email:
        return 0.5
    if linkedin:
        return 0.45
    return 0.2
