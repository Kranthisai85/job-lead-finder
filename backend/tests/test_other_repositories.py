from typing import Any

import pytest

from app.models.email_draft import EmailDraftStatus
from app.models.scraper_job import ScraperJobStatus, ScraperJobType
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.email_draft_repository import EmailDraftRepository
from app.repositories.scraper_job_repository import ScraperJobRepository


@pytest.mark.asyncio
async def test_contact_repository_operations(test_db: Any) -> None:
    company_repository = CompanyRepository()
    contact_repository = ContactRepository()

    company = await company_repository.create(
        {"name": "Lead Co", "website": "https://leadco.example"}
    )
    contact = await contact_repository.create(
        {
            "company_id": str(company.id),
            "full_name": "Jane Founder",
            "email": "jane@leadco.example",
        }
    )

    found = await contact_repository.find_one({"email": "jane@leadco.example"})
    assert found is not None
    assert found.id == contact.id

    entries = await contact_repository.find_many({"company_id": str(company.id)})
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_email_draft_repository_operations(test_db: Any) -> None:
    company_repository = CompanyRepository()
    contact_repository = ContactRepository()
    email_repository = EmailDraftRepository()

    company = await company_repository.create(
        {"name": "Outreach", "website": "https://outreach.example"}
    )
    contact = await contact_repository.create({"company_id": str(company.id), "full_name": "Alex"})

    created = await email_repository.create(
        {
            "company_id": str(company.id),
            "contact_id": str(contact.id),
            "subject": "Mobile App Opportunity",
            "body": "Hi Alex, ...",
            "status": EmailDraftStatus.DRAFT,
        }
    )

    assert created.status == EmailDraftStatus.DRAFT
    assert created.id is not None

    updated = await email_repository.update(created.id, {"status": EmailDraftStatus.APPROVED})
    assert updated is not None
    assert updated.status == EmailDraftStatus.APPROVED


@pytest.mark.asyncio
async def test_scraper_job_repository_operations(test_db: Any) -> None:
    repository = ScraperJobRepository()

    created = await repository.create(
        {
            "job_type": ScraperJobType.DISCOVERY,
            "status": ScraperJobStatus.PENDING,
        }
    )
    assert created.id is not None

    listed = await repository.list(sort=[("created_at", -1)])
    assert len(listed) >= 1

    count = await repository.count({"status": ScraperJobStatus.PENDING})
    assert count == 1
