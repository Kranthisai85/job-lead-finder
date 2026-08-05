"""Input context for the advanced qualification scoring engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.collectors.types import CompanyLead
from app.company_intelligence.models import CompanyIntelligenceReport
from app.contact_discovery.types import ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport
from app.mobile_detection.types import MobileAppDetectionResult
from app.technology.types import TechnologyReport
from app.utils.url import is_producthunt_redirect, normalize_website


def _parse_launch_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_business_email(email: str, company_website: str) -> bool:
    from app.qualification.weights import FREE_EMAIL_DOMAINS

    cleaned = email.strip().lower()
    if "@" not in cleaned:
        return False
    domain = cleaned.rsplit("@", 1)[-1]
    if domain in FREE_EMAIL_DOMAINS:
        return False
    company_host = normalize_website(company_website)
    if company_host and (domain == company_host or domain.endswith(f".{company_host}")):
        return True
    # Non-free domain email still counts as business-ish when company host unknown/PH redirect.
    if not company_host or is_producthunt_redirect(company_website):
        return domain not in FREE_EMAIL_DOMAINS
    return domain not in FREE_EMAIL_DOMAINS


class QualificationContext(BaseModel):
    """Normalized signals available for scoring (sparse or fully enriched)."""

    name: str = ""
    website: str = ""
    description: str | None = None
    source: str | None = None
    launch_date: datetime | None = None
    final_url: str | None = None
    page_title: str | None = None
    has_contact_page: bool = False
    has_careers_page: bool = False
    has_valid_business_email: bool = False
    has_any_contact: bool = False
    has_mobile_app: bool = False
    has_engineering_careers_page: bool = False
    has_remote_engineering: bool = False
    flutter_jobs: int = 0
    mobile_jobs: int = 0
    frontend_jobs: int = 0
    engineering_jobs: int = 0
    is_b2b_saas: bool = False
    is_enterprise_software: bool = False
    is_developer_tools: bool = False
    is_consumer_only: bool = False
    has_clear_icp: bool = False
    has_pricing_page: bool = False
    technologies: list[str] = Field(default_factory=list)
    hiring_text: str = ""
    corpus_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_company_lead(cls, lead: CompanyLead) -> QualificationContext:
        launch = _parse_launch_date(lead.metadata.get("launch_date")) or lead.discovered_at
        description = lead.description
        corpus_parts = [
            lead.name or "",
            description or "",
            " ".join(lead.tags or []),
            str(lead.metadata.get("topics") or ""),
        ]
        return cls(
            name=lead.name or "",
            website=lead.website or "",
            description=description,
            source=lead.source,
            launch_date=launch,
            corpus_text=" ".join(part for part in corpus_parts if part).strip(),
            metadata=dict(lead.metadata or {}),
        )

    @classmethod
    def from_enriched(
        cls,
        lead: CompanyLead,
        *,
        website_profile: WebsiteProfile | None = None,
        technology_report: TechnologyReport | None = None,
        mobile_report: MobileAppDetectionResult | None = None,
        contacts: ContactDiscoveryReport | None = None,
        hiring_report: HiringDetectionReport | None = None,
        company_intelligence: CompanyIntelligenceReport | None = None,
    ) -> QualificationContext:
        base = cls.from_company_lead(lead)
        technologies = list(base.technologies)
        hiring_parts: list[str] = [base.hiring_text]
        corpus_parts: list[str] = [base.corpus_text]

        final_url = base.final_url
        page_title = base.page_title
        description = base.description
        has_contact_page = base.has_contact_page
        has_careers_page = base.has_careers_page
        has_engineering_careers_page = base.has_engineering_careers_page
        has_remote_engineering = base.has_remote_engineering
        flutter_jobs = base.flutter_jobs
        mobile_jobs = base.mobile_jobs
        frontend_jobs = base.frontend_jobs
        engineering_jobs = base.engineering_jobs
        is_b2b_saas = base.is_b2b_saas
        is_enterprise_software = base.is_enterprise_software
        is_developer_tools = base.is_developer_tools
        is_consumer_only = base.is_consumer_only
        has_clear_icp = base.has_clear_icp
        has_pricing_page = base.has_pricing_page

        if website_profile is not None:
            final_url = website_profile.final_url or website_profile.url or final_url
            page_title = website_profile.title or page_title
            if not description:
                description = website_profile.description
            has_contact_page = bool(website_profile.contact_pages)
            career_pages = list(website_profile.career_pages)
            jobs_pages = list(website_profile.metadata.get("jobs_pages") or [])
            has_careers_page = bool(career_pages or jobs_pages)
            hiring_parts.extend(career_pages)
            hiring_parts.extend(jobs_pages)
            corpus_parts.extend(
                [
                    website_profile.title or "",
                    website_profile.description or "",
                    " ".join(website_profile.technologies or []),
                ]
            )
            technologies.extend(website_profile.technologies or [])

        if technology_report is not None:
            tech_names = [tech.name for tech in technology_report.technologies]
            technologies.extend(tech_names)
            corpus_parts.append(" ".join(tech_names))

        # Deduplicate technologies case-insensitively while preserving order.
        seen_tech: set[str] = set()
        unique_tech: list[str] = []
        for name in technologies:
            key = name.strip().lower()
            if not key or key in seen_tech:
                continue
            seen_tech.add(key)
            unique_tech.append(name.strip())

        has_mobile_app = base.has_mobile_app
        if mobile_report is not None:
            has_mobile_app = bool(mobile_report.has_mobile_app)

        has_any_contact = base.has_any_contact
        has_valid_business_email = base.has_valid_business_email
        if contacts is not None:
            emails = list(contacts.emails or [])
            for candidate in contacts.contacts or []:
                if candidate.email:
                    emails.append(candidate.email)
                if candidate.role:
                    hiring_parts.append(candidate.role)
            has_any_contact = bool(
                contacts.contact_count > 0
                or contacts.emails
                or contacts.contacts
                or contacts.linkedin_profiles
            )
            has_valid_business_email = any(
                _is_business_email(email, lead.website) for email in emails if email
            )

        if hiring_report is not None:
            flutter_jobs = hiring_report.flutter_jobs
            mobile_jobs = hiring_report.mobile_jobs
            frontend_jobs = hiring_report.frontend_jobs
            engineering_jobs = hiring_report.engineering_jobs
            has_engineering_careers_page = hiring_report.has_engineering_careers_page
            has_remote_engineering = hiring_report.has_remote_engineering
            if (
                hiring_report.jobs_found > 0
                or hiring_report.has_engineering_careers_page
                or hiring_report.provider
            ):
                has_careers_page = True
            for opportunity in hiring_report.opportunities:
                hiring_parts.append(opportunity.title)
                hiring_parts.extend(opportunity.matched_keywords)
                if opportunity.location:
                    hiring_parts.append(opportunity.location)
            if hiring_report.provider:
                hiring_parts.append(hiring_report.provider)

        if company_intelligence is not None:
            is_b2b_saas = company_intelligence.is_b2b_saas
            is_enterprise_software = company_intelligence.is_enterprise_software
            is_developer_tools = company_intelligence.is_developer_tools
            is_consumer_only = company_intelligence.is_consumer_only
            has_clear_icp = company_intelligence.has_clear_icp
            has_pricing_page = company_intelligence.has_pricing_page or bool(
                website_profile.pricing_pages if website_profile else False
            )
            for part in (
                company_intelligence.industry,
                company_intelligence.subcategory,
                company_intelligence.business_model,
                company_intelligence.target_customer,
                company_intelligence.pricing_model,
                company_intelligence.main_product,
            ):
                if part:
                    corpus_parts.append(part)
            corpus_parts.extend(company_intelligence.keywords)
            corpus_parts.extend(company_intelligence.competitors)

        if website_profile is not None and website_profile.pricing_pages:
            has_pricing_page = True

        if description:
            hiring_parts.append(description)
            corpus_parts.append(description)

        hiring_text = " ".join(part for part in hiring_parts if part).strip()
        corpus_text = " ".join(part for part in corpus_parts if part).strip()

        return cls(
            name=base.name,
            website=base.website,
            description=description,
            source=base.source,
            launch_date=base.launch_date,
            final_url=final_url,
            page_title=page_title,
            has_contact_page=has_contact_page,
            has_careers_page=has_careers_page,
            has_valid_business_email=has_valid_business_email,
            has_any_contact=has_any_contact,
            has_mobile_app=has_mobile_app,
            has_engineering_careers_page=has_engineering_careers_page,
            has_remote_engineering=has_remote_engineering,
            flutter_jobs=flutter_jobs,
            mobile_jobs=mobile_jobs,
            frontend_jobs=frontend_jobs,
            engineering_jobs=engineering_jobs,
            is_b2b_saas=is_b2b_saas,
            is_enterprise_software=is_enterprise_software,
            is_developer_tools=is_developer_tools,
            is_consumer_only=is_consumer_only,
            has_clear_icp=has_clear_icp,
            has_pricing_page=has_pricing_page,
            technologies=unique_tech,
            hiring_text=hiring_text,
            corpus_text=corpus_text,
            metadata=base.metadata,
        )

    @property
    def website_host(self) -> str:
        return normalize_website(self.website or self.final_url or "")

    @property
    def effective_url(self) -> str:
        for candidate in (self.final_url, self.website):
            if not candidate:
                continue
            cleaned = candidate.strip()
            if cleaned.startswith(("http://", "https://")):
                return cleaned
            if cleaned:
                return f"https://{cleaned}"
        return ""

    @property
    def url_scheme(self) -> str:
        return urlparse(self.effective_url).scheme.lower()
