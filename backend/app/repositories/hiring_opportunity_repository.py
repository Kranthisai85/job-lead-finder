from app.models.hiring_opportunity import HiringOpportunityDocument
from app.repositories.base_repository import BaseRepository


class HiringOpportunityRepository(BaseRepository[HiringOpportunityDocument]):
    def __init__(self) -> None:
        super().__init__(HiringOpportunityDocument)
