"""Configurable weights and thresholds for lead qualification scoring."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class QualificationWeights:
    """Point values for each scoring signal. Positive awards, negative deductions."""

    # Positive
    website_exists: int = 10
    custom_domain: int = 15
    https_enabled: int = 15
    recently_launched: int = 20
    description_long: int = 20
    contact_page_exists: int = 10
    valid_business_email: int = 20
    no_mobile_app: int = 25
    react_or_nextjs: int = 15
    flutter_mentioned: int = 30
    careers_page: int = 25
    hiring_flutter: int = 40
    hiring_mobile: int = 35
    hiring_frontend: int = 20
    engineering_careers_page: int = 15
    remote_engineering: int = 10
    intelligence_b2b_saas: int = 10
    intelligence_enterprise_software: int = 5
    intelligence_clear_icp: int = 10
    intelligence_pricing_page: int = 5
    intelligence_developer_tools: int = 10

    # Negative
    github_repository_website: int = -40
    github_pages: int = -30
    gitlab_pages: int = -30
    portfolio_website: int = -20
    demo_website: int = -20
    placeholder_landing: int = -20
    only_vercel_app: int = -20
    only_netlify_app: int = -20
    no_contact_information: int = -15
    mobile_app_exists: int = -25


@dataclass(frozen=True, slots=True)
class QualificationLevelThresholds:
    excellent: int = 80
    good: int = 60
    fair: int = 40


@dataclass(frozen=True, slots=True)
class QualificationScoringConfig:
    weights: QualificationWeights = field(default_factory=QualificationWeights)
    thresholds: QualificationLevelThresholds = field(default_factory=QualificationLevelThresholds)
    max_score: int = 100
    min_score: int = 0
    recent_launch_days: int = 30
    description_min_length: int = 80
    # Optional allow-list of signal names; empty means all signals enabled.
    enabled_signals: frozenset[str] = field(default_factory=frozenset)


DEFAULT_WEIGHTS = QualificationWeights()
DEFAULT_THRESHOLDS = QualificationLevelThresholds()
DEFAULT_SCORING_CONFIG = QualificationScoringConfig()

# Free / consumer mail hosts — not treated as valid business email.
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "mail.com",
        "gmx.com",
        "yandex.com",
    }
)

PLATFORM_DOMAINS: frozenset[str] = frozenset(
    {
        "github.com",
        "github.io",
        "gitlab.com",
        "gitlab.io",
        "vercel.app",
        "netlify.app",
        "notion.site",
        "herokuapp.com",
        "pages.dev",
        "web.app",
        "firebaseapp.com",
        "producthunt.com",
    }
)
