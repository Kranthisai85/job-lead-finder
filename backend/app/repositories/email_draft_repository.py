from app.models.email_draft import EmailDraft
from app.repositories.base_repository import BaseRepository


class EmailDraftRepository(BaseRepository[EmailDraft]):
    def __init__(self) -> None:
        super().__init__(EmailDraft)
