from datetime import datetime

from pydantic import BaseModel, Field


class CreateCompanyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str = Field(min_length=1, max_length=255)
    description: str | None = None
    industry: str | None = None
    source: str | None = None


class UpdateCompanyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    industry: str | None = None
    source: str | None = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    website: str
    description: str | None = None
    industry: str | None = None
    source: str | None = None
    created_at: datetime


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
