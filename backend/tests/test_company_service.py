from typing import Any

import pytest

from app.exceptions import DuplicateRecordError, NotFoundError
from app.repositories.company_repository import CompanyRepository
from app.schemas.company import CreateCompanyRequest, UpdateCompanyRequest
from app.services.company_service import CompanyService


@pytest.fixture()
def company_service() -> CompanyService:
    return CompanyService(CompanyRepository())


@pytest.mark.asyncio
async def test_create_company_normalizes_website(
    test_db: Any, company_service: CompanyService
) -> None:
    created = await company_service.create_company(
        CreateCompanyRequest(
            name="Acme",
            website="https://www.acme.com/",
            description="Test company",
            industry="SaaS",
            source="manual",
        )
    )

    assert created.name == "Acme"
    assert created.website == "acme.com"
    assert created.industry == "SaaS"
    assert created.source == "manual"


@pytest.mark.asyncio
async def test_create_company_duplicate_website(
    test_db: Any, company_service: CompanyService
) -> None:
    await company_service.create_company(
        CreateCompanyRequest(name="First", website="http://abc.com")
    )

    with pytest.raises(DuplicateRecordError):
        await company_service.create_company(
            CreateCompanyRequest(name="Second", website="https://abc.com/")
        )


@pytest.mark.asyncio
async def test_update_and_get_company(test_db: Any, company_service: CompanyService) -> None:
    created = await company_service.create_company(
        CreateCompanyRequest(name="Old Name", website="https://old.example")
    )

    updated = await company_service.update_company(
        created.id,
        UpdateCompanyRequest(name="New Name", industry="FinTech"),
    )
    fetched = await company_service.get_company_by_id(created.id)

    assert updated.name == "New Name"
    assert updated.industry == "FinTech"
    assert fetched.name == "New Name"


@pytest.mark.asyncio
async def test_delete_company(test_db: Any, company_service: CompanyService) -> None:
    created = await company_service.create_company(
        CreateCompanyRequest(name="Delete Me", website="https://delete.example")
    )

    await company_service.delete_company(created.id)

    with pytest.raises(NotFoundError):
        await company_service.get_company_by_id(created.id)


@pytest.mark.asyncio
async def test_search_companies(test_db: Any, company_service: CompanyService) -> None:
    await company_service.create_company(
        CreateCompanyRequest(name="Alpha Labs", website="https://alpha.example", source="ph")
    )
    await company_service.create_company(
        CreateCompanyRequest(name="Beta Inc", website="https://beta.example", source="manual")
    )

    result = await company_service.search_companies(search="alpha", page=1, page_size=10)

    assert result.total == 1
    assert result.items[0].name == "Alpha Labs"
