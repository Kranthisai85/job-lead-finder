from typing import Any

from app.exceptions import DuplicateRecordError, NotFoundError
from app.models.company import Company
from app.repositories.company_repository import CompanyRepository
from app.schemas.company import (
    CompanyListResponse,
    CompanyResponse,
    CreateCompanyRequest,
    UpdateCompanyRequest,
)
from app.utils.url import normalize_website

SORTABLE_FIELDS = {"name", "website", "source", "created_at"}


class CompanyService:
    def __init__(self, repository: CompanyRepository) -> None:
        self.repository = repository

    @staticmethod
    def _to_response(company: Company) -> CompanyResponse:
        return CompanyResponse(
            id=str(company.id),
            name=company.name,
            website=company.website,
            description=company.description,
            industry=company.tags[0] if company.tags else None,
            source=company.source,
            created_at=company.created_at,
        )

    @staticmethod
    def _build_tags(industry: str | None) -> list[str]:
        if industry and industry.strip():
            return [industry.strip()]
        return []

    async def check_duplicate_website(
        self,
        website: str,
        exclude_id: str | None = None,
    ) -> bool:
        normalized = normalize_website(website)
        existing = await self.repository.find_one({"website": normalized})
        if existing is None:
            return False
        if exclude_id and str(existing.id) == exclude_id:
            return False
        return True

    async def create_company(self, payload: CreateCompanyRequest) -> CompanyResponse:
        normalized_website = normalize_website(payload.website)
        if await self.check_duplicate_website(normalized_website):
            raise DuplicateRecordError("Company website already exists")

        company = await self.repository.create(
            {
                "name": payload.name.strip(),
                "website": normalized_website,
                "description": payload.description.strip() if payload.description else None,
                "source": payload.source.strip() if payload.source else None,
                "tags": self._build_tags(payload.industry),
            }
        )
        return self._to_response(company)

    async def update_company(
        self,
        company_id: str,
        payload: UpdateCompanyRequest,
    ) -> CompanyResponse:
        existing = await self.repository.find_by_id(company_id)
        if existing is None:
            raise NotFoundError("Company not found")

        update_data: dict[str, Any] = {}

        if payload.name is not None:
            update_data["name"] = payload.name.strip()

        if payload.website is not None:
            normalized_website = normalize_website(payload.website)
            if await self.check_duplicate_website(normalized_website, exclude_id=company_id):
                raise DuplicateRecordError("Company website already exists")
            update_data["website"] = normalized_website

        if payload.description is not None:
            update_data["description"] = payload.description.strip() or None

        if payload.source is not None:
            update_data["source"] = payload.source.strip() or None

        if payload.industry is not None:
            update_data["tags"] = self._build_tags(payload.industry)

        if not update_data:
            return self._to_response(existing)

        updated = await self.repository.update(company_id, update_data)
        if updated is None:
            raise NotFoundError("Company not found")
        return self._to_response(updated)

    async def delete_company(self, company_id: str) -> None:
        deleted = await self.repository.delete(company_id)
        if not deleted:
            raise NotFoundError("Company not found")

    async def get_company_by_id(self, company_id: str) -> CompanyResponse:
        company = await self.repository.find_by_id(company_id)
        if company is None:
            raise NotFoundError("Company not found")
        return self._to_response(company)

    async def list_companies(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> CompanyListResponse:
        return await self.search_companies(
            page=page,
            page_size=page_size,
            search=search,
            sort=sort,
            order=order,
        )

    async def search_companies(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> CompanyListResponse:
        if sort not in SORTABLE_FIELDS:
            sort = "created_at"

        sort_direction = -1 if order.lower() == "desc" else 1
        filters: dict[str, Any] = {}

        if search and search.strip():
            term = search.strip()
            filters["$or"] = [
                {"name": {"$regex": term, "$options": "i"}},
                {"website": {"$regex": term, "$options": "i"}},
                {"source": {"$regex": term, "$options": "i"}},
            ]

        result = await self.repository.paginate(
            filters=filters,
            page=page,
            page_size=page_size,
            sort=[(sort, sort_direction)],
        )

        items = [self._to_response(company) for company in result["items"]]
        return CompanyListResponse(
            items=items,
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
            total_pages=result["total_pages"],
        )
