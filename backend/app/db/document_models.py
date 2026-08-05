"""Composition root for Beanie document registration.

Imports feature-package documents here (and only here) so ``app.models`` stays
free of reverse dependencies on feature modules.
"""

from __future__ import annotations

from typing import Any

from app.company_intelligence.models import CompanyIntelligenceDocument
from app.founder_enrichment.models import FounderProfileDocument
from app.models.company import Company
from app.models.contact import Contact
from app.models.decision_maker import CompanyDecisionMakerDocument
from app.models.email_draft import EmailDraft
from app.models.hiring_opportunity import HiringOpportunityDocument
from app.models.scraper_job import ScraperJob
from app.opportunity_scoring.models import OpportunityScoreDocument

# Ordered list passed to beanie.init_beanie
DOCUMENT_MODELS: list[type[Any]] = [
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

REGISTERED_MODEL_NAMES: list[str] = [model.__name__ for model in DOCUMENT_MODELS]

__all__ = [
    "DOCUMENT_MODELS",
    "REGISTERED_MODEL_NAMES",
]
