"""Configurable weights for the opportunity (sales priority) scoring engine.

All point values live here — services must not hardcode score deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OpportunityWeights:
    """Point values for sales-priority signals. Positive = pursue, negative = deprioritize."""

    # Mobile opportunity
    no_mobile_app: int = 12
    flutter_hiring: int = 40
    mobile_hiring: int = 35
    frontend_hiring: int = 20
    pwa: int = 15
    responsive_only: int = 8
    react_native_detected: int = 8
    flutter_already_detected: int = -35
    existing_native_apps: int = -30

    # Company fit
    developer_tools: int = 12
    b2b_saas: int = 12
    enterprise: int = 8
    pricing_page: int = 5
    technology_fit: int = 10
    react_website: int = 8
    nextjs: int = 8

    # Contacts (stacking capped in service)
    founder_contact: int = 12
    decision_maker_found: int = 8
    founder_email: int = 15

    # Timing / traction
    company_age_young: int = 8
    early_startup: int = 8
    growth_startup: int = 8
    recently_launched: int = 8
    product_hunt: int = 5
    yc: int = 15
    funding_news: int = 10
    recent_hiring: int = 12

    # Bad website
    non_company_website: int = -50


@dataclass(frozen=True, slots=True)
class OpportunityPriorityThresholds:
    critical: int = 85
    high: int = 70
    medium: int = 50
    low: int = 30


@dataclass(frozen=True, slots=True)
class OpportunityScoringConfig:
    weights: OpportunityWeights = field(default_factory=OpportunityWeights)
    thresholds: OpportunityPriorityThresholds = field(default_factory=OpportunityPriorityThresholds)
    max_score: int = 100
    min_score: int = 0
    young_company_max_years: int = 5
    recent_launch_days: int = 30
    max_contact_points: int = 25
    # Empty = all signals enabled.
    enabled_signals: frozenset[str] = field(default_factory=frozenset)


DEFAULT_WEIGHTS = OpportunityWeights()
DEFAULT_THRESHOLDS = OpportunityPriorityThresholds()
DEFAULT_OPPORTUNITY_CONFIG = OpportunityScoringConfig()

FOUNDER_ROLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "founder",
        "co-founder",
        "cofounder",
        "ceo",
        "owner",
        "co founder",
    }
)

YC_KEYWORDS: tuple[str, ...] = (
    "y combinator",
    "ycombinator",
    "backed by yc",
    "yc batch",
    "yc w",
    "yc s",
    " yc ",
)

PRODUCT_HUNT_KEYWORDS: tuple[str, ...] = (
    "product hunt",
    "producthunt",
    "launched on product hunt",
)

FUNDING_KEYWORDS: tuple[str, ...] = (
    "raised",
    "funding",
    "seed round",
    "series a",
    "series b",
    "series c",
    "venture",
    "investors",
)
