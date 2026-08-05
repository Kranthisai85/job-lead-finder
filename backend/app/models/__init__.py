from app.company_intelligence.models import CompanyIntelligenceDocument
from app.founder_enrichment.models import FounderProfileDocument
from app.models.company import Company
from app.models.contact import Contact
from app.models.decision_maker import CompanyDecisionMakerDocument
from app.models.email_draft import EmailDraft
from app.models.hiring_opportunity import HiringOpportunityDocument
from app.models.scraper_job import ScraperJob
from app.opportunity_scoring.models import OpportunityScoreDocument

DOCUMENT_MODELS = [
    Company,
    Contact,
    CompanyDecisionMakerDocument,
    HiringOpportunityDocument,
    CompanyIntelligenceDocument,
    OpportunityScoreDocument,
    FounderProfileDocument,
    EmailDraft,
    ScraperJob,
]

__all__ = [
    "Company",
    "Contact",
    "CompanyDecisionMakerDocument",
    "HiringOpportunityDocument",
    "CompanyIntelligenceDocument",
    "OpportunityScoreDocument",
    "FounderProfileDocument",
    "EmailDraft",
    "ScraperJob",
    "DOCUMENT_MODELS",
]
