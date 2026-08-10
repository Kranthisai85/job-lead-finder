"""Configurable contact ranking scores and priority order."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ContactRoleScore:
    role: str
    score: int
    priority: int


# Lower priority number = higher preference.
DECISION_MAKER_ROLE_SCORES: tuple[ContactRoleScore, ...] = (
    ContactRoleScore("Founder", 100, 1),
    ContactRoleScore("Co-Founder", 98, 2),
    ContactRoleScore("CEO", 95, 3),
    ContactRoleScore("CTO", 90, 4),
    ContactRoleScore("VP Engineering", 85, 5),
    ContactRoleScore("Engineering Manager", 80, 6),
    ContactRoleScore("Product Manager", 78, 7),
    ContactRoleScore("Hiring Manager", 75, 8),
    ContactRoleScore("Mobile Lead", 72, 9),
)

GENERIC_EMAIL_SCORES: dict[str, int] = {
    "founder": 100,
    "ceo": 95,
    "cto": 90,
    "hiring": 75,
    "careers": 40,
    "jobs": 40,
    "team": 35,
    "hello": 25,
    "contact": 22,
    "support": 20,
    "info": 15,
    "sales": 18,
    "marketing": 18,
    "admin": 12,
    "hr": 30,
}

DEFAULT_NAMED_CONTACT_SCORE = 50
DEFAULT_SOCIAL_ONLY_SCORE = 35
DEFAULT_GENERIC_SCORE = 15

EXTRA_PAGE_PATHS: tuple[str, ...] = (
    "/about",
    "/team",
    "/company",
    "/contact",
    "/careers",
    "/jobs",
    "/join-us",
)

MAX_EXTRA_PAGES = 5
EXTRA_PAGE_TIMEOUT_S = 8.0

FAKE_CONTACT_LABELS: frozenset[str] = frozenset(
    {
        "terms",
        "privacy",
        "privacy policy",
        "terms of service",
        "terms of use",
        "support center",
        "documentation",
        "docs",
        "pricing",
        "marketplace",
        "sign in",
        "sign up",
        "log in",
        "login",
        "register",
        "cookie",
        "cookies",
        "cookie policy",
        "cookie banner",
        "blog",
        "blog authors",
        "authors",
        "navigation",
        "menu",
        "home",
        "about us",
        "learn more",
        "read more",
        "get started",
        "subscribe",
        "newsletter",
        "follow us",
        "all rights reserved",
    }
)

REJECTED_EMAIL_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "example",
        "test",
        "value",
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "privacy",
        "unsubscribe",
        "mailer-daemon",
        "postmaster",
        "localhost",
        "null",
        "undefined",
        "sample",
        "dummy",
        "fake",
        "governance",
        "live",
        "legal",
        "abuse",
        "newsletter",
        "mailer",
        "webmaster",
        "security",
        "compliance",
        "dmarc",
        "bounce",
        "noreply-",
    }
)

FAKE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "test.com",
        "domain.com",
        "email.com",
        "yourdomain.com",
        "company.com",
        "sentry.io",
        "localhost",
        "localdomain",
        "invalid",
    }
)

# Non-TLD domain labels that indicate placeholder / CDN / research junk.
FAKE_EMAIL_DOMAIN_LABELS: frozenset[str] = frozenset(
    {
        "example",
        "test",
        "localhost",
        "invalid",
        "fake",
        "sample",
        "dummy",
        "sentry",
        "cloudflare",
    }
)

# TLDs that are reserved, unused, or commonly appear in scraped junk.
SUSPICIOUS_EMAIL_TLDS: frozenset[str] = frozenset(
    {
        "we",
        "pay",
        "local",
        "internal",
        "invalid",
        "test",
        "localhost",
    }
)

# Product / nav / UI phrases mistaken for person names (Title Case HTML noise).
NON_PERSON_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "custom",
        "account",
        "accounts",
        "wallet",
        "wallets",
        "cloud",
        "connector",
        "connectors",
        "for",
        "and",
        "the",
        "our",
        "your",
        "with",
        "from",
        "into",
        "of",
        "to",
        "a",
        "an",
        "app",
        "apps",
        "platform",
        "product",
        "products",
        "service",
        "services",
        "solution",
        "solutions",
        "feature",
        "features",
        "tool",
        "tools",
        "api",
        "sdk",
        "dashboard",
        "portal",
        "workspace",
        "workspaces",
        "mobile",
        "web",
        "native",
        "desktop",
        "software",
        "hardware",
        "free",
        "pro",
        "premium",
        "basic",
        "advanced",
        "new",
        "best",
        "get",
        "started",
        "learn",
        "more",
        "read",
        "try",
        "buy",
        "now",
        "sign",
        "login",
        "register",
        "subscribe",
        "newsletter",
        "privacy",
        "policy",
        "terms",
        "cookie",
        "cookies",
        "support",
        "help",
        "docs",
        "documentation",
        "pricing",
        "blog",
        "home",
        "menu",
        "navigation",
        "marketplace",
        "company",
        "business",
        "enterprise",
        "startup",
        "team",
        "beta",
        "tester",
        "testers",
        "project",
        "coding",
        "browser",
        "arena",
        "monster",
        "general",
        "users",
        "customer",
        "customers",
    }
)

NAME_CONNECTIVE_TOKENS: frozenset[str] = frozenset(
    {
        "for",
        "and",
        "the",
        "of",
        "to",
        "a",
        "an",
        "with",
        "from",
        "into",
        "our",
        "your",
    }
)

DECISION_MAKER_ROLE_NAMES: frozenset[str] = frozenset(
    role.role.lower() for role in DECISION_MAKER_ROLE_SCORES
) | frozenset({"owner", "director", "vp engineering", "mobile lead", "hiring manager"})


@dataclass(frozen=True, slots=True)
class ContactRankingConfig:
    role_scores: tuple[ContactRoleScore, ...] = DECISION_MAKER_ROLE_SCORES
    generic_email_scores: dict[str, int] = field(default_factory=lambda: dict(GENERIC_EMAIL_SCORES))
    named_contact_score: int = DEFAULT_NAMED_CONTACT_SCORE
    social_only_score: int = DEFAULT_SOCIAL_ONLY_SCORE
    generic_score: int = DEFAULT_GENERIC_SCORE
    max_score: int = 100
    min_score: int = 0


DEFAULT_CONTACT_RANKING = ContactRankingConfig()
