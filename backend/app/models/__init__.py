from app.models.company import Company
from app.models.contact import Contact
from app.models.email_draft import EmailDraft
from app.models.scraper_job import ScraperJob

DOCUMENT_MODELS = [Company, Contact, EmailDraft, ScraperJob]

__all__ = [
    "Company",
    "Contact",
    "EmailDraft",
    "ScraperJob",
    "DOCUMENT_MODELS",
]
