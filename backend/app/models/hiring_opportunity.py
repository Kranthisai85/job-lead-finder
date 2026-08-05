from pymongo import IndexModel

from app.models.base import BaseDocument


class HiringOpportunityDocument(BaseDocument):
    """Persisted hiring opportunity, separate from Contact/Company documents."""

    company_id: str
    title: str
    department: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    url: str | None = None
    provider: str | None = None
    confidence: float | None = None
    matched_keywords: list[str] = []
    seniority: str | None = None
    source_page: str | None = None

    class Settings:
        name = "hiring_opportunities"
        indexes = [
            IndexModel([("company_id", 1)]),
            IndexModel([("url", 1)], sparse=True),
            IndexModel([("company_id", 1), ("title", 1)]),
            IndexModel([("provider", 1)]),
            IndexModel([("created_at", -1)]),
        ]
