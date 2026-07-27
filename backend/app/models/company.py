from pydantic import Field
from pymongo import IndexModel

from app.models.base import BaseDocument


class Company(BaseDocument):
    name: str
    website: str
    description: str | None = None
    source: str | None = None
    country: str | None = None
    has_mobile_app: bool | None = None
    is_flutter_lead: bool | None = None
    tags: list[str] = Field(default_factory=list)

    class Settings:
        name = "companies"
        indexes = [
            IndexModel([("website", 1)], unique=True),
            IndexModel([("name", 1)]),
            IndexModel([("source", 1)]),
            IndexModel([("has_mobile_app", 1), ("is_flutter_lead", 1)]),
            IndexModel([("created_at", -1)]),
        ]
