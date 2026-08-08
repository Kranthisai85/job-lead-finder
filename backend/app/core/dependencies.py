from fastapi import Depends

from app.email_queue.service import EmailQueueService
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.email_draft_repository import EmailDraftRepository
from app.repositories.scraper_job_repository import ScraperJobRepository
from app.sender_profile.service import SenderProfileService
from app.services.company_service import CompanyService


def get_company_repository() -> CompanyRepository:
    return CompanyRepository()


def get_company_service(
    repository: CompanyRepository = Depends(get_company_repository),
) -> CompanyService:
    return CompanyService(repository)


def get_contact_repository() -> ContactRepository:
    return ContactRepository()


def get_email_draft_repository() -> EmailDraftRepository:
    return EmailDraftRepository()


def get_scraper_job_repository() -> ScraperJobRepository:
    return ScraperJobRepository()


def get_email_queue_service() -> EmailQueueService:
    return EmailQueueService()


def get_sender_profile_service() -> SenderProfileService:
    return SenderProfileService()
