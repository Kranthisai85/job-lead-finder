"""Core Beanie document models only.

Feature packages must not be imported here — that creates circular imports when
feature documents inherit from ``app.models.base.BaseDocument``.

Beanie registration of all documents (core + feature) lives in
``app.db.document_models``.
"""

from app.models.base import BaseDocument
from app.models.company import Company
from app.models.contact import Contact
from app.models.decision_maker import CompanyDecisionMakerDocument
from app.models.email_draft import EmailDraft
from app.models.hiring_opportunity import HiringOpportunityDocument
from app.models.scraper_job import ScraperJob

__all__ = [
    "BaseDocument",
    "Company",
    "Contact",
    "CompanyDecisionMakerDocument",
    "HiringOpportunityDocument",
    "EmailDraft",
    "ScraperJob",
]
