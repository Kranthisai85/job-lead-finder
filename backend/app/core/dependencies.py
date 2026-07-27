from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.email_draft_repository import EmailDraftRepository
from app.repositories.scraper_job_repository import ScraperJobRepository


def get_company_repository() -> CompanyRepository:
    return CompanyRepository()


def get_contact_repository() -> ContactRepository:
    return ContactRepository()


def get_email_draft_repository() -> EmailDraftRepository:
    return EmailDraftRepository()


def get_scraper_job_repository() -> ScraperJobRepository:
    return ScraperJobRepository()
