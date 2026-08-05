from app.founder_enrichment.models import FounderProfileDocument
from app.repositories.base_repository import BaseRepository


class FounderProfileRepository(BaseRepository[FounderProfileDocument]):
    def __init__(self) -> None:
        super().__init__(FounderProfileDocument)
