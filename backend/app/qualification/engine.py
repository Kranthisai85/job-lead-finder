"""Backward-compatible qualification engine facade over QualificationScoringEngine."""

from __future__ import annotations

from app.collectors.types import CompanyLead
from app.company_intelligence.models import CompanyIntelligenceReport
from app.contact_discovery.types import ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.context import QualificationContext
from app.qualification.scoring_engine import QualificationScoringEngine
from app.qualification.types import QualificationResult
from app.qualification.weights import (
    DEFAULT_SCORING_CONFIG,
    QualificationLevelThresholds,
    QualificationScoringConfig,
    QualificationWeights,
)
from app.technology.types import TechnologyReport


class QualificationEngine:
    """Facade that preserves the historical `.qualify(CompanyLead)` API."""

    def __init__(
        self,
        scoring_engine: QualificationScoringEngine | None = None,
        *,
        passing_score: int | None = None,
        config: QualificationScoringConfig | None = None,
        # Legacy kwargs accepted for backward compatibility with older callers/tests.
        rules: list[object] | None = None,
        enabled_rules: set[str] | None = None,
        max_score: int = 100,
    ) -> None:
        base = config or DEFAULT_SCORING_CONFIG
        thresholds = base.thresholds
        if passing_score is not None:
            thresholds = QualificationLevelThresholds(
                excellent=max(passing_score, base.thresholds.excellent),
                good=passing_score,
                fair=min(passing_score, base.thresholds.fair),
            )
        effective = QualificationScoringConfig(
            weights=base.weights,
            thresholds=thresholds,
            max_score=max_score,
            min_score=base.min_score,
            recent_launch_days=base.recent_launch_days,
            description_min_length=base.description_min_length,
            enabled_signals=base.enabled_signals,
        )
        self.scoring_engine = (
            scoring_engine
            if scoring_engine is not None and passing_score is None and config is None
            else QualificationScoringEngine(effective)
        )
        self.passing_score = effective.thresholds.good
        self.max_score = effective.max_score
        self.config = effective
        # Retained for introspection compatibility.
        self.rules = rules or []
        self.enabled_rules = enabled_rules or set()

    def qualify(self, lead: CompanyLead) -> QualificationResult:
        context = QualificationContext.from_company_lead(lead)
        return self.scoring_engine.score(context)

    def qualify_context(self, context: QualificationContext) -> QualificationResult:
        return self.scoring_engine.score(context)

    def qualify_enriched(
        self,
        lead: CompanyLead,
        *,
        website_profile: WebsiteProfile | None = None,
        technology_report: TechnologyReport | None = None,
        mobile_report: MobileAppDetectionResult | None = None,
        contacts: ContactDiscoveryReport | None = None,
        hiring_report: HiringDetectionReport | None = None,
        company_intelligence: CompanyIntelligenceReport | None = None,
    ) -> QualificationResult:
        context = QualificationContext.from_enriched(
            lead,
            website_profile=website_profile,
            technology_report=technology_report,
            mobile_report=mobile_report,
            contacts=contacts,
            hiring_report=hiring_report,
            company_intelligence=company_intelligence,
        )
        return self.scoring_engine.score(context)


def build_default_engine(
    *,
    passing_score: int | None = None,
    enabled_rules: set[str] | None = None,
    config: QualificationScoringConfig | None = None,
    weights: QualificationWeights | None = None,
) -> QualificationEngine:
    from app.core.config import settings

    base = config or DEFAULT_SCORING_CONFIG
    if weights is not None:
        base = QualificationScoringConfig(
            weights=weights,
            thresholds=base.thresholds,
            max_score=base.max_score,
            min_score=base.min_score,
            recent_launch_days=base.recent_launch_days,
            description_min_length=base.description_min_length,
            enabled_signals=base.enabled_signals,
        )
    score = (
        passing_score
        if passing_score is not None
        else getattr(settings, "qualification_passing_score", base.thresholds.good)
    )
    return QualificationEngine(
        passing_score=score,
        enabled_rules=enabled_rules,
        max_score=base.max_score,
        config=base,
    )
