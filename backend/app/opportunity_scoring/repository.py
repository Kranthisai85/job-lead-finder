from app.opportunity_scoring.models import OpportunityScoreDocument
from app.repositories.base_repository import BaseRepository


class OpportunityScoreRepository(BaseRepository[OpportunityScoreDocument]):
    def __init__(self) -> None:
        super().__init__(OpportunityScoreDocument)
