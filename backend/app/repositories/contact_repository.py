from app.models.contact import Contact
from app.repositories.base_repository import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    def __init__(self) -> None:
        super().__init__(Contact)
