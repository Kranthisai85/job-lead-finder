from datetime import datetime

from beanie import Document, before_event
from beanie.odm.actions import Insert, Replace, SaveChanges
from pydantic import Field

from app.core.timezone import now_app


class BaseDocument(Document):
    created_at: datetime = Field(default_factory=now_app)
    updated_at: datetime = Field(default_factory=now_app)

    @before_event(Insert)
    def set_created_at(self) -> None:
        now = now_app()
        self.created_at = now
        self.updated_at = now

    @before_event(Replace, SaveChanges)
    def set_updated_at(self) -> None:
        self.updated_at = now_app()
