"""Production-grade weighted qualification scoring engine."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from app.qualification.context import QualificationContext
from app.qualification.types import QualificationLevel, QualificationResult
from app.qualification.weights import (
    DEFAULT_SCORING_CONFIG,
    PLATFORM_DOMAINS,
    QualificationScoringConfig,
)
from app.utils.url import (
    is_blog_host,
    is_intermediate_or_cdn_host,
    is_producthunt_host,
    is_producthunt_redirect,
    is_usable_company_website,
)

SignalFn = Callable[[QualificationContext, QualificationScoringConfig], tuple[int, str, bool]]


def _host_is_platform(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def _contains_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _hiring_for(text: str, role_keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    hiring_markers = ("hir", "job", "career", "recruit", "opening", "we are looking", "engineer")
    if not any(marker in lowered for marker in hiring_markers):
        # Careers page URL alone is weak; require role keyword with employment context OR
        # explicit "hiring <role>" style phrases.
        return bool(
            re.search(
                r"\b(hiring|hire|looking for)\b.{0,40}\b("
                + "|".join(re.escape(k) for k in role_keywords)
                + r")\b",
                lowered,
            )
        )
    return any(keyword in lowered for keyword in role_keywords)


class QualificationScoringEngine:
    """Weighted scorer producing score, level, reasons, and warnings."""

    def __init__(self, config: QualificationScoringConfig | None = None) -> None:
        self.config = config or DEFAULT_SCORING_CONFIG
        self._signals: list[tuple[str, SignalFn]] = [
            ("website_exists", self._signal_website_exists),
            ("custom_domain", self._signal_custom_domain),
            ("https_enabled", self._signal_https_enabled),
            ("recently_launched", self._signal_recently_launched),
            ("description_long", self._signal_description_long),
            ("contact_page_exists", self._signal_contact_page),
            ("valid_business_email", self._signal_business_email),
            ("no_mobile_app", self._signal_no_mobile_app),
            ("react_or_nextjs", self._signal_react_or_next),
            ("flutter_mentioned", self._signal_flutter_mentioned),
            ("careers_page", self._signal_careers_page),
            ("hiring_flutter", self._signal_hiring_flutter),
            ("hiring_mobile", self._signal_hiring_mobile),
            ("hiring_frontend", self._signal_hiring_frontend),
            ("engineering_careers_page", self._signal_engineering_careers_page),
            ("remote_engineering", self._signal_remote_engineering),
            ("intelligence_b2b_saas", self._signal_intelligence_b2b_saas),
            ("intelligence_enterprise_software", self._signal_intelligence_enterprise),
            ("intelligence_clear_icp", self._signal_intelligence_clear_icp),
            ("intelligence_pricing_page", self._signal_intelligence_pricing_page),
            ("intelligence_developer_tools", self._signal_intelligence_developer_tools),
            ("github_repository_website", self._signal_github_repository),
            ("github_pages", self._signal_github_pages),
            ("gitlab_pages", self._signal_gitlab_pages),
            ("portfolio_website", self._signal_portfolio),
            ("demo_website", self._signal_demo),
            ("placeholder_landing", self._signal_placeholder),
            ("only_vercel_app", self._signal_vercel_only),
            ("only_netlify_app", self._signal_netlify_only),
            ("no_contact_information", self._signal_no_contact),
            ("mobile_app_exists", self._signal_mobile_app_exists),
            ("producthunt_or_platform_website", self._signal_producthunt_or_platform),
            ("intermediate_or_blog_host", self._signal_intermediate_or_blog),
        ]

    def score(self, context: QualificationContext) -> QualificationResult:
        total = 0
        reasons: list[str] = []
        warnings: list[str] = []
        enabled = self.config.enabled_signals

        for name, signal in self._signals:
            if enabled and name not in enabled:
                continue
            points, message, is_warning = signal(context, self.config)
            if points == 0 and not message:
                continue
            total += points
            if message:
                if is_warning or points < 0:
                    warnings.append(message)
                else:
                    reasons.append(message)

        clamped = max(self.config.min_score, min(self.config.max_score, total))
        level = self._level_for(clamped)
        qualified = clamped >= self.config.thresholds.good
        if context.website and not is_usable_company_website(context.website):
            qualified = False

        return QualificationResult(
            qualified=qualified,
            score=clamped,
            level=level,
            reasons=reasons,
            warnings=warnings,
        )

    def _level_for(self, score: int) -> QualificationLevel:
        thresholds = self.config.thresholds
        if score >= thresholds.excellent:
            return QualificationLevel.EXCELLENT
        if score >= thresholds.good:
            return QualificationLevel.GOOD
        if score >= thresholds.fair:
            return QualificationLevel.FAIR
        return QualificationLevel.POOR

    def _signal_website_exists(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if not context.website.strip():
            return 0, "Website is missing", True
        if not is_usable_company_website(context.website):
            return 0, "", False
        points = config.weights.website_exists
        return points, f"+{points} Website exists", False

    def _signal_custom_domain(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        if not host:
            return 0, "", False
        if not is_usable_company_website(context.website):
            return 0, "", False
        if is_producthunt_redirect(context.website):
            return 0, "", False
        if any(_host_is_platform(host, platform) for platform in PLATFORM_DOMAINS):
            return 0, "", False
        points = config.weights.custom_domain
        return points, f"+{points} Custom domain ({host})", False

    def _signal_https_enabled(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if not is_usable_company_website(context.website):
            return 0, "", False
        if context.url_scheme == "https":
            points = config.weights.https_enabled
            return points, f"+{points} HTTPS enabled", False
        # Domain-only websites (no scheme) are treated as HTTPS-capable defaults.
        if context.website and not context.website.startswith(("http://", "https://")):
            if not is_producthunt_redirect(context.website):
                points = config.weights.https_enabled
                return points, f"+{points} HTTPS enabled", False
        return 0, "", False

    def _signal_recently_launched(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.launch_date is None:
            return 0, "", False
        launch = context.launch_date
        if launch.tzinfo is None:
            launch = launch.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - launch.astimezone(timezone.utc)).days
        if 0 <= age_days <= config.recent_launch_days:
            points = config.weights.recently_launched
            return points, f"+{points} Recently launched ({age_days} days ago)", False
        return 0, "", False

    def _signal_description_long(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        description = (context.description or "").strip()
        if len(description) > config.description_min_length:
            points = config.weights.description_long
            return (
                points,
                f"+{points} Description longer than {config.description_min_length} characters",
                False,
            )
        return 0, "", False

    def _signal_contact_page(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_contact_page:
            points = config.weights.contact_page_exists
            return points, f"+{points} Contact page exists", False
        return 0, "", False

    def _signal_business_email(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_valid_business_email:
            points = config.weights.valid_business_email
            return points, f"+{points} Valid business email discovered", False
        return 0, "", False

    def _signal_no_mobile_app(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        # Only award after crawl enrichment (final_url set) confirms no app.
        if not context.final_url:
            return 0, "", False
        if not is_usable_company_website(context.website):
            return 0, "", False
        if not context.has_mobile_app:
            points = config.weights.no_mobile_app
            return points, f"+{points} No mobile app detected", False
        return 0, "", False

    def _signal_react_or_next(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        names = {name.lower() for name in context.technologies}
        corpus = context.corpus_text.lower()
        matched = any(token in names for token in ("react", "next.js", "nextjs", "next"))
        if not matched:
            matched = "react" in corpus or "next.js" in corpus or "nextjs" in corpus
        if matched:
            points = config.weights.react_or_nextjs
            return points, f"+{points} React or Next.js detected", False
        return 0, "", False

    def _signal_flutter_mentioned(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        names = {name.lower() for name in context.technologies}
        corpus = f"{context.corpus_text} {context.hiring_text}".lower()
        if "flutter" in names or "flutter" in corpus:
            points = config.weights.flutter_mentioned
            return points, f"+{points} Flutter mentioned", False
        return 0, "", False

    def _signal_careers_page(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_careers_page:
            points = config.weights.careers_page
            return points, f"+{points} Careers page detected", False
        return 0, "", False

    def _signal_hiring_flutter(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.flutter_jobs > 0 or _hiring_for(
            context.hiring_text or context.corpus_text, ("flutter",)
        ):
            points = config.weights.hiring_flutter
            return points, f"+{points} Hiring Flutter", False
        return 0, "", False

    def _signal_hiring_mobile(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.mobile_jobs > 0 or _hiring_for(
            context.hiring_text or context.corpus_text,
            ("mobile", "ios", "android", "react native"),
        ):
            points = config.weights.hiring_mobile
            return points, f"+{points} Hiring Mobile", False
        return 0, "", False

    def _signal_hiring_frontend(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.frontend_jobs > 0 or _hiring_for(
            context.hiring_text or context.corpus_text,
            ("frontend", "front-end", "front end", "react", "vue", "angular"),
        ):
            points = config.weights.hiring_frontend
            return points, f"+{points} Hiring Frontend", False
        return 0, "", False

    def _signal_engineering_careers_page(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_engineering_careers_page or context.engineering_jobs > 0:
            points = config.weights.engineering_careers_page
            return points, f"+{points} Engineering careers page", False
        return 0, "", False

    def _signal_remote_engineering(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_remote_engineering:
            points = config.weights.remote_engineering
            return points, f"+{points} Remote engineering role", False
        return 0, "", False

    def _signal_intelligence_b2b_saas(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.is_consumer_only:
            return 0, "", False
        if context.is_b2b_saas:
            points = config.weights.intelligence_b2b_saas
            return points, f"+{points} B2B SaaS", False
        return 0, "", False

    def _signal_intelligence_enterprise(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.is_enterprise_software:
            points = config.weights.intelligence_enterprise_software
            return points, f"+{points} Enterprise software", False
        return 0, "", False

    def _signal_intelligence_clear_icp(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_clear_icp:
            points = config.weights.intelligence_clear_icp
            return points, f"+{points} Clear ICP", False
        return 0, "", False

    def _signal_intelligence_pricing_page(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_pricing_page:
            points = config.weights.intelligence_pricing_page
            return points, f"+{points} Pricing page exists", False
        return 0, "", False

    def _signal_intelligence_developer_tools(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.is_consumer_only:
            return 0, "", False
        if context.is_developer_tools:
            points = config.weights.intelligence_developer_tools
            return points, f"+{points} Developer tools", False
        return 0, "", False

    def _signal_github_repository(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        url = context.effective_url.lower()
        if host == "github.com" or "github.com/" in url:
            path = urlparse(context.effective_url).path
            parts = [part for part in path.split("/") if part]
            # github.com/<user>/<repo> is a repository homepage.
            if len(parts) >= 2 and parts[0] not in {
                "topics",
                "features",
                "pricing",
                "marketplace",
            }:
                points = config.weights.github_repository_website
                return points, f"{points} GitHub repository used as website", True
        return 0, "", False

    def _signal_github_pages(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        if _host_is_platform(host, "github.io"):
            points = config.weights.github_pages
            return points, f"{points} GitHub Pages", True
        return 0, "", False

    def _signal_gitlab_pages(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        if _host_is_platform(host, "gitlab.io"):
            points = config.weights.gitlab_pages
            return points, f"{points} GitLab Pages", True
        return 0, "", False

    def _signal_portfolio(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        corpus = f"{context.page_title or ''} {context.description or ''} {context.corpus_text}"
        if _contains_keywords(
            corpus,
            ("portfolio", "personal website", "my work", "selected works"),
        ):
            points = config.weights.portfolio_website
            return points, f"{points} Portfolio website", True
        return 0, "", False

    def _signal_demo(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        corpus = f"{context.website} {context.page_title or ''} {context.description or ''}"
        if _contains_keywords(corpus, ("demo.", "/demo", " demo ", "sandbox", "example app")):
            points = config.weights.demo_website
            return points, f"{points} Demo website", True
        host = context.website_host
        if host.startswith("demo.") or ".demo." in host:
            points = config.weights.demo_website
            return points, f"{points} Demo website", True
        return 0, "", False

    def _signal_placeholder(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        corpus = f"{context.page_title or ''} {context.description or ''} {context.corpus_text}"
        if _contains_keywords(
            corpus,
            (
                "coming soon",
                "under construction",
                "lorem ipsum",
                "placeholder",
                "launching soon",
                "site is being built",
            ),
        ):
            points = config.weights.placeholder_landing
            return points, f"{points} Placeholder landing page", True
        return 0, "", False

    def _signal_vercel_only(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        if _host_is_platform(host, "vercel.app"):
            points = config.weights.only_vercel_app
            return points, f"{points} Only vercel.app domain", True
        return 0, "", False

    def _signal_netlify_only(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        host = context.website_host
        if _host_is_platform(host, "netlify.app"):
            points = config.weights.only_netlify_app
            return points, f"{points} Only netlify.app domain", True
        return 0, "", False

    def _signal_no_contact(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if not context.has_any_contact and not context.has_contact_page:
            if context.final_url or context.has_careers_page or context.technologies:
                points = config.weights.no_contact_information
                return points, f"{points} No contact information", True
        return 0, "", False

    def _signal_mobile_app_exists(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if context.has_mobile_app:
            points = config.weights.mobile_app_exists
            return points, f"{points} Mobile app already exists", True
        return 0, "", False

    def _signal_producthunt_or_platform(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if is_producthunt_redirect(context.website) or is_producthunt_host(context.website):
            points = config.weights.producthunt_or_platform_website
            return points, f"{points} Product Hunt / platform website", True
        host = context.website_host
        if host and any(_host_is_platform(host, platform) for platform in PLATFORM_DOMAINS):
            # Covered by github/vercel signals for some hosts; still penalize PH/CF.
            if _host_is_platform(host, "producthunt.com") or _host_is_platform(
                host, "cloudflare.com"
            ):
                points = config.weights.producthunt_or_platform_website
                return points, f"{points} Product Hunt / platform website", True
        return 0, "", False

    def _signal_intermediate_or_blog(
        self, context: QualificationContext, config: QualificationScoringConfig
    ) -> tuple[int, str, bool]:
        if is_intermediate_or_cdn_host(context.website) or is_blog_host(context.website):
            points = config.weights.intermediate_or_blog_host
            return points, f"{points} Intermediate CDN or blog host", True
        return 0, "", False


def build_default_scoring_engine(
    config: QualificationScoringConfig | None = None,
) -> QualificationScoringEngine:
    return QualificationScoringEngine(config=config or DEFAULT_SCORING_CONFIG)
