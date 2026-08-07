"""Extract scoring signals from CompleteLead using only existing evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from app.contact_discovery.validators import is_valid_email
from app.lead_scoring.types import LeadScoreSignals
from app.pipeline.types import CompleteLead
from app.utils.url import (
    is_blog_host,
    is_intermediate_or_cdn_host,
    is_producthunt_host,
    is_producthunt_redirect,
    is_usable_company_website,
)

_RECENT_LAUNCH_DAYS = 30

_PRODUCT_CATEGORY_HINTS = (
    "saas",
    "software",
    "platform",
    "developer",
    "devtools",
    "ai",
    "product",
    "startup",
    "app",
    "fintech",
    "edtech",
    "b2b",
)

_AGENCY_HINTS = (
    "recruitment",
    "recruiting",
    "staffing",
    "headhunt",
    "talent agency",
    "recruitment agency",
    "hiring agency",
    "consulting agency",
    "marketing agency",
    "digital agency",
    "design agency",
    "creative agency",
    "outsourcing",
)

_PLATFORM_HOST_SUFFIXES = (
    "github.io",
    "gitlab.io",
    "vercel.app",
    "netlify.app",
    "herokuapp.com",
    "pages.dev",
    "web.app",
    "firebaseapp.com",
    "notion.site",
    "carrd.co",
)


def extract_signals(lead: CompleteLead) -> LeadScoreSignals:
    return LeadScoreSignals(
        recently_launched=_recently_launched(lead),
        has_mobile_app=_mobile_app_flag(lead),
        is_product_company=_is_product_company(lead),
        has_founder_or_contact=_has_founder_or_contact(lead),
        has_valid_email=_has_valid_email(lead),
        is_agency_or_recruitment=_is_agency_or_recruitment(lead),
        is_generic_website=_is_generic_website(lead),
    )


def _recently_launched(lead: CompleteLead) -> bool:
    source = (lead.startup.source or "").strip().lower()
    if "producthunt" in source or source == "product_hunt":
        return True

    launch = _launch_date(lead)
    if launch is None:
        return False
    if launch.tzinfo is None:
        launch = launch.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - launch.astimezone(timezone.utc)).days
    return 0 <= age_days <= _RECENT_LAUNCH_DAYS


def _launch_date(lead: CompleteLead) -> datetime | None:
    metadata = {}
    if lead.website_profile and isinstance(lead.website_profile.metadata, dict):
        metadata = lead.website_profile.metadata
    raw = metadata.get("launch_date")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _mobile_app_flag(lead: CompleteLead) -> bool | None:
    if lead.mobile_report is not None:
        return bool(lead.mobile_report.has_mobile_app)
    if lead.lead_intelligence is not None and lead.lead_intelligence.mobile_detection is not None:
        return bool(lead.lead_intelligence.mobile_detection.has_mobile_app)
    return None


def _corpus(lead: CompleteLead) -> str:
    parts: list[str] = [
        lead.startup.name or "",
        lead.startup.description or "",
    ]
    profile = lead.company_profile
    if profile:
        parts.extend(
            [
                profile.business_category or "",
                profile.industry or "",
                profile.product_type or "",
                profile.short_description or "",
                profile.target_audience or "",
            ]
        )
    intel = lead.company_intelligence
    if intel:
        parts.extend(
            [
                intel.industry or "",
                intel.business_model or "",
                intel.main_product or "",
                " ".join(intel.keywords or []),
            ]
        )
    if lead.website_profile:
        parts.extend(
            [
                lead.website_profile.title or "",
                lead.website_profile.description or "",
            ]
        )
    return " ".join(parts).lower()


def _is_product_company(lead: CompleteLead) -> bool:
    profile = lead.company_profile
    if profile:
        product_type = (profile.product_type or "").strip().lower()
        if product_type in {"saas", "platform", "mobile app", "software", "api", "marketplace"}:
            return True
        category = (profile.business_category or "").strip().lower()
        if any(hint in category for hint in _PRODUCT_CATEGORY_HINTS):
            return True
        industry = (profile.industry or "").strip().lower()
        if any(hint in industry for hint in _PRODUCT_CATEGORY_HINTS):
            return True

    intel = lead.company_intelligence
    if intel is not None:
        if intel.is_b2b_saas or intel.is_developer_tools or intel.is_enterprise_software:
            return True

    corpus = _corpus(lead)
    return any(hint in corpus for hint in ("saas", "software product", "startup", "b2b"))


def _has_founder_or_contact(lead: CompleteLead) -> bool:
    if lead.founder_enrichment and lead.founder_enrichment.founders_found > 0:
        return True
    if lead.founder_enrichment and lead.founder_enrichment.primary_founder is not None:
        return True
    if lead.contacts and lead.contacts.contacts:
        for contact in lead.contacts.contacts:
            name = (contact.full_name or contact.first_name or "").strip()
            if name:
                return True
    if lead.lead_intelligence and lead.lead_intelligence.best_contact:
        best = lead.lead_intelligence.best_contact
        name = (best.full_name or best.first_name or "").strip()
        if name:
            return True
    return False


def _has_valid_email(lead: CompleteLead) -> bool:
    if lead.lead_intelligence and lead.lead_intelligence.best_contact:
        email = lead.lead_intelligence.best_contact.email
        if email and is_valid_email(email):
            return True
    if lead.contacts and lead.contacts.contacts:
        for contact in lead.contacts.contacts:
            if contact.email and is_valid_email(contact.email):
                return True
    if lead.contacts and lead.contacts.emails:
        for email in lead.contacts.emails:
            if is_valid_email(email):
                return True
    if lead.founder_enrichment:
        for founder in lead.founder_enrichment.founders or []:
            if founder.email and is_valid_email(founder.email):
                return True
        primary = lead.founder_enrichment.primary_founder
        if primary and primary.email and is_valid_email(primary.email):
            return True
    return False


def _is_agency_or_recruitment(lead: CompleteLead) -> bool:
    profile = lead.company_profile
    if profile:
        category = (profile.business_category or "").strip().lower()
        industry = (profile.industry or "").strip().lower()
        if category in {"agencies", "agency", "recruitment", "staffing"}:
            return True
        if "agency" in industry or "recruit" in industry or "staffing" in industry:
            return True

    intel = lead.company_intelligence
    if intel and intel.industry:
        industry = intel.industry.strip().lower()
        if industry in {"agency", "recruitment", "staffing"} or "agency" in industry:
            return True

    corpus = _corpus(lead)
    return any(hint in corpus for hint in _AGENCY_HINTS)


def _is_generic_website(lead: CompleteLead) -> bool:
    website = (lead.startup.website or "").strip()
    if not website:
        return True
    if not is_usable_company_website(website):
        return True
    if is_producthunt_host(website) or is_producthunt_redirect(website):
        return True
    if is_blog_host(website) or is_intermediate_or_cdn_host(website):
        return True

    cleaned = website if website.startswith(("http://", "https://")) else f"https://{website}"
    host = (urlparse(cleaned).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for suffix in _PLATFORM_HOST_SUFFIXES:
        if host == suffix or host.endswith(f".{suffix}"):
            return True
    return False
