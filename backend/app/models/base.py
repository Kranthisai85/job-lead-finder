from datetime import datetime, timezone

from beanie import Document, before_event
from beanie.odm.actions import Insert, Replace, SaveChanges
from pydantic import Field


class BaseDocument(Document):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @before_event(Insert)
    def set_created_at(self) -> None:
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now

    @before_event(Replace, SaveChanges)
    def set_updated_at(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
