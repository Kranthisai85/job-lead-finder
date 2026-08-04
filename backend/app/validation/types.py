from pydantic import BaseModel, Field

from app.contact_discovery.types import ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.email_patterns.types import EmailPatternReport
from app.intelligence.types import LeadIntelligence
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.technology.types import TechnologyReport

DECISION_MAKER_ROLES = {
    "founder",
    "co-founder",
    "ceo",
    "cto",
    "owner",
    "director",
}


class StartupSeed(BaseModel):
    name: str
    website: str
    description: str | None = None
    source: str = "sample_data"


class CompanyValidationResult(BaseModel):
    name: str
    website: str
    website_reachable: bool = False
    technologies: list[str] = Field(default_factory=list)
    mobile_app: bool = False
    play_store: bool = False
    app_store: bool = False
    qualification_pass: bool = False
    qualification_score: int = 0
    contact_emails_found: int = 0
    decision_makers: int = 0
    email_pattern: str | None = None
    lead_score: float = 0.0
    is_good_lead: bool = False
    errors: list[str] = Field(default_factory=list)

    website_profile: WebsiteProfile | None = None
    technology_report: TechnologyReport | None = None
    mobile_detection: MobileAppDetectionResult | None = None
    qualification: QualificationResult | None = None
    contact_discovery: ContactDiscoveryReport | None = None
    email_patterns: EmailPatternReport | None = None
    lead_intelligence: LeadIntelligence | None = None


class ValidationSummary(BaseModel):
    companies_processed: int = 0
    reachable: int = 0
    qualified: int = 0
    mobile_apps: int = 0
    emails_found: int = 0
    technology_detection_success: int = 0
    average_lead_score: float = 0.0
    good_leads: int = 0


class ValidationReport(BaseModel):
    results: list[CompanyValidationResult] = Field(default_factory=list)
    summary: ValidationSummary = Field(default_factory=ValidationSummary)


def compute_lead_score(
    *,
    qualification_score: int,
    contact_emails_found: int,
    technology_count: int,
    mobile_app: bool,
    is_good_lead: bool,
) -> float:
    score = float(qualification_score)
    score += min(20.0, contact_emails_found * 5.0)
    score += min(10.0, float(technology_count))
    if mobile_app:
        score -= 15.0
    if is_good_lead:
        score += 10.0
    return max(0.0, min(100.0, score))


def count_decision_makers(contact_discovery: ContactDiscoveryReport | None) -> int:
    if contact_discovery is None:
        return 0
    count = 0
    for contact in contact_discovery.contacts:
        role = (contact.role or "").lower()
        if role in DECISION_MAKER_ROLES:
            count += 1
    return count
