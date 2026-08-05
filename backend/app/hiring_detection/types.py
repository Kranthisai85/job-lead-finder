from __future__ import annotations

from pydantic import BaseModel, Field


class HiringOpportunity(BaseModel):
    title: str
    department: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    url: str | None = None
    provider: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)
    seniority: str | None = None
    source_page: str | None = None


class HiringDetectionReport(BaseModel):
    url: str
    jobs_found: int = 0
    flutter_jobs: int = 0
    mobile_jobs: int = 0
    frontend_jobs: int = 0
    engineering_jobs: int = 0
    provider: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    opportunities: list[HiringOpportunity] = Field(default_factory=list)
    pages_scanned: list[str] = Field(default_factory=list)
    best_job: HiringOpportunity | None = None
    has_engineering_careers_page: bool = False
    has_remote_engineering: bool = False
