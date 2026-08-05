"""Company Intelligence v2 enrichment service."""

from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.company_intelligence.extractor import (
    BUSINESS_MODEL_RULES,
    MAX_EXTRA_PAGES,
    PAGE_TIMEOUT_S,
    TARGET_CUSTOMER_RULES,
    build_corpus,
    candidate_intelligence_urls,
    detect_company_stage,
    detect_funding_status,
    detect_pricing_model,
    estimate_maturity,
    estimate_team_size,
    extract_competitors,
    extract_faq_text,
    extract_hero_text,
    extract_keywords,
    extract_main_product,
    extract_meta_signals,
    extract_opportunities,
    extract_pain_points,
    extract_structured_data,
    infer_industry,
    infer_subcategory,
    page_looks_like,
    score_label,
    validate_enum,
)
from app.company_intelligence.models import (
    BUSINESS_MODELS,
    COMPANY_STAGES,
    PRICING_MODELS,
    TARGET_CUSTOMERS,
    CompanyIntelligenceReport,
)
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport
from app.technology.types import TechnologyReport


class CompanyIntelligenceService:
    """Enrich company understanding after hiring detection, before qualification."""

    def __init__(
        self,
        *,
        fetch_extra_pages: bool = True,
        http_client: httpx.Client | None = None,
        max_pages: int = MAX_EXTRA_PAGES,
        timeout_s: float = PAGE_TIMEOUT_S,
    ) -> None:
        self.fetch_extra_pages = fetch_extra_pages
        self._http_client = http_client
        self.max_pages = max_pages
        self.timeout_s = timeout_s
        self.logger = get_logger(__name__)

    def analyze(
        self,
        profile: WebsiteProfile,
        *,
        technology_report: TechnologyReport | None = None,
        hiring_report: HiringDetectionReport | None = None,
    ) -> CompanyIntelligenceReport:
        source_url = profile.final_url or profile.url
        pages: list[tuple[str, str]] = []
        homepage_html = str((profile.metadata or {}).get("html", ""))
        if homepage_html:
            pages.append((source_url, homepage_html))

        if self.fetch_extra_pages:
            pages.extend(self._load_extra_pages(profile, source_url))

        corpus_parts: list[str] = [
            profile.title or "",
            profile.description or "",
            " ".join(profile.technologies or []),
        ]
        pages_scanned: list[str] = []
        has_pricing_page = bool(profile.pricing_pages)
        structured: dict[str, Any] = {}
        meta: dict[str, str] = {}
        hero = ""
        faq = ""
        soup_home: BeautifulSoup | None = None

        for page_url, html in pages:
            pages_scanned.append(page_url)
            soup = BeautifulSoup(html or "", "html.parser")
            if soup_home is None:
                soup_home = soup
            page_meta = extract_meta_signals(soup)
            meta.update(page_meta)
            page_structured = extract_structured_data(soup)
            structured.update(page_structured)
            hero_text = extract_hero_text(soup)
            faq_text = extract_faq_text(soup)
            if hero_text:
                hero = f"{hero} {hero_text}".strip()
            if faq_text:
                faq = f"{faq} {faq_text}".strip()
            corpus_parts.append(hero_text)
            corpus_parts.append(faq_text)
            corpus_parts.append(page_meta.get("description", ""))
            corpus_parts.append(page_meta.get("og:description", ""))
            corpus_parts.append(page_meta.get("keywords", ""))
            corpus_parts.append(str(page_structured.get("description") or ""))
            corpus_parts.append(str(page_structured.get("industry") or ""))
            if page_looks_like(page_url, "pricing", "plan"):
                has_pricing_page = True
            corpus_parts.append(" ".join(soup.stripped_strings)[:4000])

        if profile.pricing_pages:
            has_pricing_page = True

        if technology_report is not None:
            corpus_parts.append(" ".join(tech.name for tech in technology_report.technologies))

        hiring_jobs = hiring_report.jobs_found if hiring_report else 0
        engineering_jobs = hiring_report.engineering_jobs if hiring_report else 0
        if hiring_report is not None:
            for opportunity in hiring_report.opportunities:
                corpus_parts.append(opportunity.title)
                corpus_parts.extend(opportunity.matched_keywords)
            if hiring_report.provider:
                corpus_parts.append(hiring_report.provider)

        corpus = build_corpus(*corpus_parts)
        signals: list[str] = []

        business_model, model_hits = score_label(corpus, BUSINESS_MODEL_RULES)
        signals.extend(f"business_model:{hit}" for hit in model_hits)
        target_customer, customer_hits = score_label(corpus, TARGET_CUSTOMER_RULES)
        signals.extend(f"target_customer:{hit}" for hit in customer_hits)

        # Prefer Developer Tool when strong developer signals and SaaS also matches.
        if "for developers" in corpus or "devtools" in corpus or "developer tools" in corpus:
            if business_model in {None, "SaaS"}:
                business_model = "Developer Tool"
                signals.append("business_model:Developer Tool:developer_override")

        pricing_model = detect_pricing_model(corpus, has_pricing_page=has_pricing_page)
        if has_pricing_page:
            signals.append("pricing_page:detected")
        company_stage = detect_company_stage(corpus, hiring_jobs=hiring_jobs)
        funding_status = detect_funding_status(corpus)
        keywords = extract_keywords(corpus)
        industry = infer_industry(business_model, keywords, corpus)
        subcategory = infer_subcategory(corpus, business_model)
        competitors = extract_competitors(corpus)
        pain_points = extract_pain_points(corpus)
        opportunities = extract_opportunities(corpus)
        if hiring_report and hiring_report.flutter_jobs > 0:
            opportunities.append("Flutter hiring / mobile engineering demand")
        if hiring_report and hiring_report.engineering_jobs > 0:
            opportunities.append("Active engineering hiring")

        main_product = None
        if soup_home is not None:
            main_product = extract_main_product(soup_home, structured, profile.title)
        team_size = estimate_team_size(
            corpus, hiring_jobs=hiring_jobs, engineering_jobs=engineering_jobs
        )
        maturity = estimate_maturity(company_stage, funding_status)

        business_model = validate_enum(business_model, BUSINESS_MODELS)
        target_customer = validate_enum(target_customer, TARGET_CUSTOMERS)
        pricing_model = validate_enum(pricing_model, PRICING_MODELS) or "Unknown"
        company_stage = validate_enum(company_stage, COMPANY_STAGES)

        is_b2b_saas = bool(
            business_model == "SaaS"
            and target_customer in {"B2B", "Enterprise", "SMB", "Startup", "Developers"}
        )
        is_enterprise_software = bool(
            business_model == "Enterprise Software"
            or (
                target_customer == "Enterprise"
                and business_model in {"SaaS", "Enterprise Software", None}
            )
        )
        is_developer_tools = bool(
            business_model == "Developer Tool" or target_customer == "Developers"
        )
        is_consumer_only = bool(
            (business_model == "Consumer App" or target_customer == "B2C")
            and target_customer not in {"B2B", "Enterprise", "SMB", "Startup", "Developers"}
            and business_model
            not in {"SaaS", "Developer Tool", "Enterprise Software", "FinTech", "Healthcare"}
        )
        has_clear_icp = bool(business_model and target_customer)

        confidence = self._confidence(
            business_model=business_model,
            target_customer=target_customer,
            pricing_model=pricing_model,
            industry=industry,
            has_pricing_page=has_pricing_page,
            pages_scanned=len(pages_scanned),
            structured=bool(structured),
            hiring_jobs=hiring_jobs,
        )

        report = CompanyIntelligenceReport(
            url=source_url,
            industry=industry,
            subcategory=subcategory,
            business_model=business_model,
            target_customer=target_customer,
            pricing_model=pricing_model,
            company_stage=company_stage,
            estimated_team_size=team_size,
            estimated_maturity=maturity,
            competitors=competitors,
            keywords=keywords,
            pain_points=pain_points,
            opportunities=list(dict.fromkeys(opportunities)),
            funding_status=funding_status,
            confidence=confidence,
            main_product=main_product,
            product_category=subcategory or business_model,
            has_pricing_page=has_pricing_page,
            is_b2b_saas=is_b2b_saas,
            is_enterprise_software=bool(is_enterprise_software),
            is_developer_tools=bool(is_developer_tools),
            is_consumer_only=is_consumer_only,
            has_clear_icp=has_clear_icp,
            pages_scanned=pages_scanned,
            signals=signals,
        )

        self.logger.info(
            (
                "url=%s industry=%s business_model=%s target_customer=%s "
                "pricing_model=%s stage=%s pricing_page=%s clear_icp=%s "
                "b2b_saas=%s developer_tools=%s confidence=%.2f"
            ),
            report.url,
            report.industry,
            report.business_model,
            report.target_customer,
            report.pricing_model,
            report.company_stage,
            report.has_pricing_page,
            report.has_clear_icp,
            report.is_b2b_saas,
            report.is_developer_tools,
            report.confidence,
        )
        return report

    def _confidence(
        self,
        *,
        business_model: str | None,
        target_customer: str | None,
        pricing_model: str | None,
        industry: str | None,
        has_pricing_page: bool,
        pages_scanned: int,
        structured: bool,
        hiring_jobs: int,
    ) -> float:
        score = 0.15
        if business_model:
            score += 0.2
        if target_customer:
            score += 0.15
        if industry:
            score += 0.1
        if pricing_model and pricing_model != "Unknown":
            score += 0.1
        if has_pricing_page:
            score += 0.1
        if pages_scanned > 1:
            score += 0.1
        if structured:
            score += 0.05
        if hiring_jobs > 0:
            score += 0.05
        return round(min(1.0, score), 2)

    def _load_extra_pages(self, profile: WebsiteProfile, base_url: str) -> list[tuple[str, str]]:
        metadata = profile.metadata or {}
        link_pool: list[str] = []
        link_pool.extend(profile.pricing_pages or [])
        link_pool.extend(self._flatten(metadata.get("about_pages", [])))
        link_pool.extend(self._flatten(metadata.get("internal_links", [])))
        link_pool.extend(self._flatten(metadata.get("external_links", [])))

        candidates = candidate_intelligence_urls(base_url, link_pool)
        fetched: list[tuple[str, str]] = []
        seen: set[str] = {(base_url or "").rstrip("/").lower()}
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_s,
                headers={"User-Agent": "LeadFinderBot/1.0 (+https://lead-finder.local)"},
            )
        assert client is not None
        try:
            for url in candidates:
                key = url.rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                if len(fetched) >= self.max_pages:
                    break
                try:
                    response = client.get(url)
                    if response.status_code >= 400:
                        continue
                    content_type = response.headers.get("content-type", "")
                    if content_type and "html" not in content_type.lower():
                        continue
                    html = response.text
                    if not html or len(html) < 40:
                        continue
                    fetched.append((str(response.url), html))
                except Exception as exc:
                    self.logger.debug("company_intelligence_page_failed url=%s error=%s", url, exc)
        finally:
            if owns_client:
                client.close()
        return fetched

    @staticmethod
    def _flatten(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
