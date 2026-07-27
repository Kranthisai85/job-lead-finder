from fastapi import APIRouter, Depends, Query, status
from starlette.responses import Response

from app.core.dependencies import get_company_service
from app.core.response import success_response
from app.schemas.common import APIResponse
from app.schemas.company import (
    CompanyListResponse,
    CompanyResponse,
    CreateCompanyRequest,
    UpdateCompanyRequest,
)
from app.services.company_service import CompanyService

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=APIResponse[CompanyListResponse])
async def list_companies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    service: CompanyService = Depends(get_company_service),
) -> APIResponse[CompanyListResponse]:
    data = await service.list_companies(
        page=page,
        page_size=page_size,
        search=search,
        sort=sort,
        order=order,
    )
    return success_response(message="Companies retrieved successfully", data=data.model_dump())


@router.post("", response_model=APIResponse[CompanyResponse], status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CreateCompanyRequest,
    service: CompanyService = Depends(get_company_service),
) -> APIResponse[CompanyResponse]:
    data = await service.create_company(payload)
    return success_response(message="Company created successfully", data=data.model_dump())


@router.get("/{company_id}", response_model=APIResponse[CompanyResponse])
async def get_company(
    company_id: str,
    service: CompanyService = Depends(get_company_service),
) -> APIResponse[CompanyResponse]:
    data = await service.get_company_by_id(company_id)
    return success_response(message="Company retrieved successfully", data=data.model_dump())


@router.patch("/{company_id}", response_model=APIResponse[CompanyResponse])
async def update_company(
    company_id: str,
    payload: UpdateCompanyRequest,
    service: CompanyService = Depends(get_company_service),
) -> APIResponse[CompanyResponse]:
    data = await service.update_company(company_id, payload)
    return success_response(message="Company updated successfully", data=data.model_dump())


@router.delete("/{company_id}", response_model=APIResponse[dict[str, str]])
async def delete_company(
    company_id: str,
    response: Response,
    service: CompanyService = Depends(get_company_service),
) -> APIResponse[dict[str, str]]:
    await service.delete_company(company_id)
    response.status_code = status.HTTP_200_OK
    return success_response(message="Company deleted successfully", data={"id": company_id})
