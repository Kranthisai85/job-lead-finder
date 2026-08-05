"""Opportunity Scoring Engine — sales priority score (not lead quality)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.company_intelligence.models import CompanyIntelligenceReport
from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactDiscoveryReport
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport
from app.mobile_detection.types import MobileAppDetectionResult
from app.opportunity_scoring.models import OpportunityScoreReport
from app.opportunity_scoring.weights import (
    DEFAULT_OPPORTUNITY_CONFIG,
    FOUNDER_ROLE_KEYWORDS,
    FUNDING_KEYWORDS,
    PRODUCT_HUNT_KEYWORDS,
    YC_KEYWORDS,
    OpportunityScoringConfig,
    OpportunityWeights,
)
from app.technology.types import TechnologyReport
from app.utils.url import is_usable_company_website


SignalResult = tuple[int, str, bool]  # points, message, is_warning
SignalFn = Callable[..., SignalResult]

_CONTACT_SIGNAL_KEYS = ("founder_contact", "decision_maker_found", "founder_email")


class OpportunityScoringService:
    """Score how hot a lead is for outreach (Flutter / mobile agency sales priority)."""

    def __init__(self, config: OpportunityScoringConfig | None = None) -> None:
        self.config = config or DEFAULT_OPPORTUNITY_CONFIG
        self.logger = get_logger(__name__)
        self._signals: list[tuple[str, SignalFn]] = [
            ("no_mobile_app", self._signal_no_mobile_app),
            ("flutter_hiring", self._signal_flutter_hiring),
            ("mobile_hiring", self._signal_mobile_hiring),
            ("frontend_hiring", self._signal_frontend_hiring),
            ("developer_tools", self._signal_developer_tools),
            ("b2b_saas", self._signal_b2b_saas),
            ("enterprise", self._signal_enterprise),
            ("pricing_page", self._signal_pricing_page),
            ("founder_contact", self._signal_founder_contact),
            ("decision_maker_found", self._signal_decision_maker),
            ("founder_email", self._signal_founder_email),
            ("company_age_young", self._signal_company_age),
            ("early_startup", self._signal_early_startup),
            ("growth_startup", self._signal_growth_startup),
            ("recently_launched", self._signal_recently_launched),
            ("product_hunt", self._signal_product_hunt),
            ("yc", self._signal_yc),
            ("funding_news", self._signal_funding_news),
            ("recent_hiring", self._signal_recent_hiring),
            ("technology_fit", self._signal_technology_fit),
            ("react_website", self._signal_react),
            ("nextjs", self._signal_nextjs),
            ("pwa", self._signal_pwa),
            ("responsive_only", self._signal_responsive_only),
            ("react_native_detected", self._signal_react_native),
            ("flutter_already_detected", self._signal_flutter_already),
            ("existing_native_apps", self._signal_existing_native),
            ("non_company_website", self._signal_non_company_website),
        ]

    def score(
        self,
        *,
        url: str = "",
        source: str | None = None,
        website_profile: WebsiteProfile | None = None,
        company_profile: CompanyProfile | None = None,
        technology_report: TechnologyReport | None = None,
        mobile_report: MobileAppDetectionResult | None = None,
        contacts: ContactDiscoveryReport | None = None,
        hiring_report: HiringDetectionReport | None = None,
        company_intelligence: CompanyIntelligenceReport | None = None,
        launch_date: datetime | None = None,
        description: str | None = None,
    ) -> OpportunityScoreReport:
        ctx = _OpportunityContext(
            url=url
            or (website_profile.final_url if website_profile else "")
            or (website_profile.url if website_profile else ""),
            source=source or "",
            website_profile=website_profile,
            company_profile=company_profile,
            technology_report=technology_report,
            mobile_report=mobile_report,
            contacts=contacts,
            hiring_report=hiring_report,
            company_intelligence=company_intelligence,
            launch_date=launch_date,
            description=description or "",
        )

        total = 0
        reasons: list[str] = []
        warnings: list[str] = []
        breakdown: dict[str, int] = {}
        enabled = self.config.enabled_signals
        evaluated = 0

        for name, signal in self._signals:
            if enabled and name not in enabled:
                continue
            points, message, is_warning = signal(ctx, self.config.weights)
            evaluated += 1
            if points == 0 and not message:
                continue
            total += points
            breakdown[name] = points
            if message:
                if is_warning or points < 0:
                    warnings.append(message)
                else:
                    reasons.append(message)

        # Cap overlapping contact signals so founder contact+email cannot alone dominate.
        contact_total = sum(breakdown.get(key, 0) for key in _CONTACT_SIGNAL_KEYS)
        max_contact = self.config.max_contact_points
        if contact_total > max_contact:
            excess = contact_total - max_contact
            total -= excess
            warnings.append(f"Contact signal cap applied (-{excess})")

        clamped = max(self.config.min_score, min(self.config.max_score, total))
        priority = self._priority_for(clamped, ctx)
        level = self._level_for(clamped, priority)
        has_founder_email = ctx.has_founder_email
        action = self._recommended_action(priority, has_founder_email=has_founder_email)
        confidence = self._confidence(ctx, evaluated=evaluated, fired=len(breakdown))

        report = OpportunityScoreReport(
            url=ctx.url,
            overall_score=clamped,
            priority=priority,
            opportunity_level=level,
            reasons=reasons,
            warnings=warnings,
            recommended_action=action,
            confidence=confidence,
            score_breakdown=breakdown,
        )

        self.logger.info(
            (
                "url=%s overall_score=%d priority=%s opportunity_level=%s "
                "recommended_action=%s confidence=%.2f reasons=%d warnings=%d"
            ),
            report.url,
            report.overall_score,
            report.priority,
            report.opportunity_level,
            report.recommended_action,
            report.confidence,
            len(report.reasons),
            len(report.warnings),
        )
        return report

    def _priority_for(self, score: int, ctx: "_OpportunityContext") -> str:
        t = self.config.thresholds
        if score >= t.critical:
            # Critical requires a strong mobile/Flutter hiring signal — not soft stacks alone.
            if self._has_critical_hiring_signal(ctx):
                return "Critical"
            if score >= t.high:
                return "High"
            return "Medium"
        if score >= t.high:
            return "High"
        if score >= t.medium:
            return "Medium"
        if score >= t.low:
            return "Low"
        return "Very Low"

    def _level_for(self, score: int, priority: str) -> str:
        if priority == "Critical":
            return "Exceptional"
        t = self.config.thresholds
        if score >= t.high:
            return "Strong"
        if score >= t.medium:
            return "Moderate"
        if score >= t.low:
            return "Weak"
        return "Negligible"

    @staticmethod
    def _has_critical_hiring_signal(ctx: "_OpportunityContext") -> bool:
        if ctx.hiring_report is None:
            return False
        return ctx.hiring_report.flutter_jobs > 0 or ctx.hiring_report.mobile_jobs > 0

    @staticmethod
    def _recommended_action(priority: str, *, has_founder_email: bool) -> str:
        if priority == "Critical":
            return "Send immediately"
        if priority == "High":
            return "Send founder email" if has_founder_email else "Send immediately"
        if priority == "Medium":
            return "Research manually"
        if priority == "Low":
            return "Wait"
        return "Ignore"

    @staticmethod
    def _confidence(ctx: "_OpportunityContext", *, evaluated: int, fired: int) -> float:
        score = 0.2
        if ctx.website_profile is not None:
            score += 0.1
        if ctx.technology_report is not None:
            score += 0.1
        if ctx.mobile_report is not None:
            score += 0.1
        if ctx.contacts is not None:
            score += 0.1
        if ctx.hiring_report is not None:
            score += 0.15
        if ctx.company_intelligence is not None:
            score += 0.15
        if fired:
            score += min(0.15, 0.02 * fired)
        if evaluated:
            score = min(1.0, score)
        return round(min(1.0, score), 2)

    # --- signals ---

    def _signal_no_mobile_app(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        # Only award when mobile detection explicitly ran and found no app.
        if ctx.mobile_report is not None and not ctx.mobile_report.has_mobile_app:
            points = weights.no_mobile_app
            return points, f"+{points} No mobile app", False
        return 0, "", False

    def _signal_flutter_hiring(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.hiring_report and ctx.hiring_report.flutter_jobs > 0:
            points = weights.flutter_hiring
            return points, f"+{points} Flutter hiring", False
        return 0, "", False

    def _signal_mobile_hiring(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.hiring_report and ctx.hiring_report.mobile_jobs > 0:
            points = weights.mobile_hiring
            return points, f"+{points} Mobile hiring", False
        return 0, "", False

    def _signal_frontend_hiring(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.hiring_report and ctx.hiring_report.frontend_jobs > 0:
            points = weights.frontend_hiring
            return points, f"+{points} Frontend hiring", False
        return 0, "", False

    def _signal_developer_tools(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.company_intelligence and ctx.company_intelligence.is_developer_tools:
            points = weights.developer_tools
            return points, f"+{points} Developer tools", False
        return 0, "", False

    def _signal_b2b_saas(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.company_intelligence and ctx.company_intelligence.is_b2b_saas:
            points = weights.b2b_saas
            return points, f"+{points} B2B SaaS", False
        return 0, "", False

    def _signal_enterprise(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.company_intelligence and ctx.company_intelligence.is_enterprise_software:
            points = weights.enterprise
            return points, f"+{points} Enterprise", False
        return 0, "", False

    def _signal_pricing_page(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        has_pricing = bool(
            (ctx.company_intelligence and ctx.company_intelligence.has_pricing_page)
            or (ctx.website_profile and ctx.website_profile.pricing_pages)
        )
        if has_pricing:
            points = weights.pricing_page
            return points, f"+{points} Pricing page", False
        return 0, "", False

    def _signal_founder_contact(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_founder_contact:
            points = weights.founder_contact
            return points, f"+{points} Founder contact", False
        return 0, "", False

    def _signal_decision_maker(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        # Avoid double-counting when a founder contact already fired.
        if ctx.has_founder_contact:
            return 0, "", False
        if ctx.contacts and ctx.contacts.decision_makers_found > 0:
            points = weights.decision_maker_found
            return points, f"+{points} Decision maker found", False
        return 0, "", False

    def _signal_founder_email(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_founder_email:
            points = weights.founder_email
            return points, f"+{points} Founder email", False
        return 0, "", False

    def _signal_company_age(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        age = ctx.company_age_years
        if age is None:
            return 0, "", False
        if 0 <= age <= self.config.young_company_max_years:
            points = weights.company_age_young
            return points, f"+{points} Young company ({age}y)", False
        return 0, "", False

    def _signal_early_startup(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        stage = ctx.company_stage
        if stage in {"Idea", "MVP", "Early Startup"}:
            points = weights.early_startup
            return points, f"+{points} Early startup ({stage})", False
        return 0, "", False

    def _signal_growth_startup(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        stage = ctx.company_stage
        if stage in {"Growth", "Scale-up"}:
            points = weights.growth_startup
            return points, f"+{points} Growth startup ({stage})", False
        return 0, "", False

    def _signal_recently_launched(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.launch_date is None:
            return 0, "", False
        launch = ctx.launch_date
        if launch.tzinfo is None:
            launch = launch.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - launch.astimezone(timezone.utc)).days
        if 0 <= age_days <= self.config.recent_launch_days:
            points = weights.recently_launched
            return points, f"+{points} Recently launched ({age_days}d)", False
        return 0, "", False

    def _signal_product_hunt(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.is_product_hunt:
            points = weights.product_hunt
            return points, f"+{points} Product Hunt", False
        return 0, "", False

    def _signal_yc(self, ctx: "_OpportunityContext", weights: OpportunityWeights) -> SignalResult:
        if ctx.is_yc:
            points = weights.yc
            return points, f"+{points} YC", False
        return 0, "", False

    def _signal_funding_news(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_funding_news:
            points = weights.funding_news
            return points, f"+{points} Funding news", False
        return 0, "", False

    def _signal_recent_hiring(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.hiring_report and ctx.hiring_report.jobs_found > 0:
            points = weights.recent_hiring
            return points, f"+{points} Recent hiring", False
        return 0, "", False

    def _signal_technology_fit(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        # Web stack present + no native app = good Flutter pitch fit.
        if ctx.has_web_stack and not ctx.has_mobile_app:
            points = weights.technology_fit
            return points, f"+{points} Technology fit", False
        return 0, "", False

    def _signal_react(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_tech("react") and not ctx.has_tech("react native"):
            points = weights.react_website
            return points, f"+{points} React website", False
        return 0, "", False

    def _signal_nextjs(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_tech("next.js") or ctx.has_tech("nextjs") or ctx.has_tech("next"):
            points = weights.nextjs
            return points, f"+{points} Next.js", False
        return 0, "", False

    def _signal_pwa(self, ctx: "_OpportunityContext", weights: OpportunityWeights) -> SignalResult:
        if ctx.has_tech("pwa") or "progressive web" in ctx.corpus:
            points = weights.pwa
            return points, f"+{points} PWA", False
        return 0, "", False

    def _signal_responsive_only(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.is_responsive_only:
            points = weights.responsive_only
            return points, f"+{points} Responsive only", False
        return 0, "", False

    def _signal_react_native(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_tech("react native") or "react native" in ctx.corpus:
            points = weights.react_native_detected
            label = f"+{points}" if points >= 0 else str(points)
            return points, f"{label} React Native detected", points < 0
        return 0, "", False

    def _signal_flutter_already(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_tech("flutter") or (
            ctx.mobile_report
            and any("flutter" in item.lower() for item in ctx.mobile_report.evidence)
        ):
            points = weights.flutter_already_detected
            return points, f"{points} Flutter already detected", True
        return 0, "", False

    def _signal_existing_native(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.has_mobile_app and (
            ctx.has_store_links
            or (
                ctx.mobile_report
                and (ctx.mobile_report.android_detected or ctx.mobile_report.ios_detected)
            )
        ):
            # Skip if only Flutter (already penalized) and no store — still penalize native stores.
            points = weights.existing_native_apps
            return points, f"{points} Existing native apps", True
        return 0, "", False

    def _signal_non_company_website(
        self, ctx: "_OpportunityContext", weights: OpportunityWeights
    ) -> SignalResult:
        if ctx.url and not is_usable_company_website(ctx.url):
            points = weights.non_company_website
            return points, f"{points} Non-company website", True
        return 0, "", False


class _OpportunityContext:
    """Normalized inputs for opportunity signals."""

    def __init__(
        self,
        *,
        url: str,
        source: str,
        website_profile: WebsiteProfile | None,
        company_profile: CompanyProfile | None,
        technology_report: TechnologyReport | None,
        mobile_report: MobileAppDetectionResult | None,
        contacts: ContactDiscoveryReport | None,
        hiring_report: HiringDetectionReport | None,
        company_intelligence: CompanyIntelligenceReport | None,
        launch_date: datetime | None,
        description: str,
    ) -> None:
        self.url = url
        self.source = source
        self.website_profile = website_profile
        self.company_profile = company_profile
        self.technology_report = technology_report
        self.mobile_report = mobile_report
        self.contacts = contacts
        self.hiring_report = hiring_report
        self.company_intelligence = company_intelligence
        self.launch_date = launch_date
        self.description = description

        tech_names: list[str] = []
        if technology_report:
            tech_names.extend(t.name for t in technology_report.technologies)
        if website_profile:
            tech_names.extend(website_profile.technologies or [])
        self._tech_lower = {name.strip().lower() for name in tech_names if name}

        parts = [
            description,
            website_profile.title if website_profile else "",
            website_profile.description if website_profile else "",
            source,
        ]
        if company_intelligence:
            parts.extend(
                [
                    company_intelligence.industry or "",
                    company_intelligence.business_model or "",
                    company_intelligence.funding_status or "",
                    company_intelligence.company_stage or "",
                    " ".join(company_intelligence.keywords),
                    " ".join(company_intelligence.signals),
                ]
            )
        if company_profile:
            parts.extend(
                [
                    company_profile.short_description or "",
                    company_profile.industry or "",
                    company_profile.business_category or "",
                ]
            )
        self.corpus = " ".join(p for p in parts if p).lower()

    def has_tech(self, name: str) -> bool:
        needle = name.lower()
        if needle in self._tech_lower:
            return True
        return any(needle in item for item in self._tech_lower)

    @property
    def has_web_stack(self) -> bool:
        return any(
            self.has_tech(token)
            for token in ("react", "next.js", "nextjs", "vue", "angular", "svelte")
        )

    @property
    def has_mobile_app(self) -> bool:
        if self.mobile_report is not None:
            return bool(self.mobile_report.has_mobile_app)
        return self.has_store_links

    @property
    def has_store_links(self) -> bool:
        if self.website_profile is None:
            return False
        return bool(self.website_profile.app_store_links or self.website_profile.play_store_links)

    @property
    def is_responsive_only(self) -> bool:
        if self.has_mobile_app:
            return False
        html = ""
        if self.website_profile and self.website_profile.metadata:
            html = str(self.website_profile.metadata.get("html") or "").lower()
        viewport = "viewport" in html or "responsive" in self.corpus
        return viewport and not self.has_mobile_app

    @property
    def company_stage(self) -> str | None:
        if self.company_intelligence and self.company_intelligence.company_stage:
            return self.company_intelligence.company_stage
        return None

    @property
    def company_age_years(self) -> int | None:
        if self.company_profile and self.company_profile.founded_year:
            year = self.company_profile.founded_year
            current = datetime.now(timezone.utc).year
            if 1970 <= year <= current:
                return current - year
        return None

    @property
    def is_product_hunt(self) -> bool:
        source = (self.source or "").lower()
        if "producthunt" in source or "product_hunt" in source or "product-hunt" in source:
            return True
        return any(token in self.corpus for token in PRODUCT_HUNT_KEYWORDS)

    @property
    def is_yc(self) -> bool:
        return any(token in f" {self.corpus} " for token in YC_KEYWORDS)

    @property
    def has_funding_news(self) -> bool:
        if self.company_intelligence and self.company_intelligence.funding_status:
            return True
        return any(token in self.corpus for token in FUNDING_KEYWORDS)

    @property
    def has_founder_contact(self) -> bool:
        if not self.contacts:
            return False
        for maker in self.contacts.decision_makers:
            if _is_founder_role(maker.role):
                return True
        for contact in self.contacts.contacts:
            if _is_founder_role(contact.role) or _is_founder_role(contact.company_role):
                return True
        return False

    @property
    def has_founder_email(self) -> bool:
        if not self.contacts:
            return False
        for maker in self.contacts.decision_makers:
            if maker.email and _is_founder_role(maker.role):
                return True
        for contact in self.contacts.contacts:
            if contact.email and (
                _is_founder_role(contact.role) or _is_founder_role(contact.company_role)
            ):
                return True
        return False


def _is_founder_role(role: str | None) -> bool:
    if not role:
        return False
    lowered = role.strip().lower()
    if lowered in FOUNDER_ROLE_KEYWORDS:
        return True
    return any(token in lowered for token in FOUNDER_ROLE_KEYWORDS)
