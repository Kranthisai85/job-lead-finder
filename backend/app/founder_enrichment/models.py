"""Founder enrichment DTOs and persistence document."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pymongo import IndexModel

from app.models.base import BaseDocument


class FounderProfile(BaseModel):
    """Enriched founder / primary decision-maker profile."""

    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    role: str | None = None
    email: str | None = None
    bio: str | None = None
    github: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    personal_website: str | None = None
    location: str | None = None
    avatar_url: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_page: str | None = None
    discovery_source: str | None = None


class FounderEnrichmentReport(BaseModel):
    """Result of founder enrichment. Empty when no founder is found."""

    url: str = ""
    founders_found: int = 0
    founders: list[FounderProfile] = Field(default_factory=list)
    primary_founder: FounderProfile | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    empty: bool = True


class FounderProfileDocument(BaseDocument):
    """Persisted founder profile — separate from Contact / Company models."""

    company_id: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    role: str | None = None
    email: str | None = None
    bio: str | None = None
    github: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    personal_website: str | None = None
    location: str | None = None
    avatar_url: str | None = None
    confidence: float | None = None
    source_page: str | None = None
    discovery_source: str | None = None
    is_primary: bool = False

    class Settings:
        name = "founder_profiles"
        indexes = [
            IndexModel([("company_id", 1)]),
            IndexModel([("email", 1)], sparse=True),
            IndexModel([("linkedin", 1)], sparse=True),
            IndexModel([("company_id", 1), ("full_name", 1)]),
            IndexModel([("created_at", -1)]),
        ]
