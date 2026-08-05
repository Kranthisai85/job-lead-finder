from app.models.decision_maker import CompanyDecisionMakerDocument
from app.repositories.base_repository import BaseRepository


class DecisionMakerRepository(BaseRepository[CompanyDecisionMakerDocument]):
    def __init__(self) -> None:
        super().__init__(CompanyDecisionMakerDocument)
