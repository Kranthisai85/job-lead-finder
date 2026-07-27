from enum import Enum

from pymongo import IndexModel

from app.models.base import BaseDocument


class EmailDraftStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    QUEUED = "queued"
    SENT = "sent"


class EmailDraft(BaseDocument):
    company_id: str
    contact_id: str
    subject: str
    body: str
    status: EmailDraftStatus = EmailDraftStatus.DRAFT
    llm_model: str | None = None

    class Settings:
        name = "email_drafts"
        indexes = [
            IndexModel([("company_id", 1), ("contact_id", 1)]),
            IndexModel([("status", 1), ("created_at", -1)]),
            IndexModel([("updated_at", -1)]),
        ]
