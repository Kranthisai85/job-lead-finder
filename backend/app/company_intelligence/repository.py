from app.company_intelligence.models import CompanyIntelligenceDocument
from app.repositories.base_repository import BaseRepository


class CompanyIntelligenceRepository(BaseRepository[CompanyIntelligenceDocument]):
    def __init__(self) -> None:
        super().__init__(CompanyIntelligenceDocument)
