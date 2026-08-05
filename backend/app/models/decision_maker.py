from pymongo import IndexModel

from app.models.base import BaseDocument


class CompanyDecisionMakerDocument(BaseDocument):
    """Persisted decision maker, separate from generic Contact records."""

    company_id: str
    name: str
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    github: str | None = None
    twitter: str | None = None
    confidence: float | None = None
    source_page: str | None = None
    contact_score: int | None = None
    contact_id: str | None = None

    class Settings:
        name = "company_decision_makers"
        indexes = [
            IndexModel([("company_id", 1)]),
            IndexModel([("email", 1)], sparse=True),
            IndexModel([("linkedin", 1)], sparse=True),
            IndexModel([("github", 1)], sparse=True),
            IndexModel([("company_id", 1), ("name", 1), ("role", 1)]),
            IndexModel([("created_at", -1)]),
        ]
