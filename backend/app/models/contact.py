from pymongo import IndexModel

from app.models.base import BaseDocument


class Contact(BaseDocument):
    company_id: str
    full_name: str
    role: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    confidence_score: float | None = None

    class Settings:
        name = "contacts"
        indexes = [
            IndexModel([("company_id", 1)]),
            IndexModel([("email", 1)], sparse=True),
            IndexModel([("full_name", 1)]),
            IndexModel([("created_at", -1)]),
        ]
