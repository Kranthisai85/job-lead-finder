from app.collectors.types import CompanyLead
from app.core.logger import get_logger
from app.qualification.engine import QualificationEngine, build_default_engine
from app.qualification.types import QualificationResult


class QualificationService:
    def __init__(self, engine: QualificationEngine | None = None) -> None:
        self.engine = engine or build_default_engine()
        self.logger = get_logger(__name__)

    def qualify(self, lead: CompanyLead) -> QualificationResult:
        result = self.engine.qualify(lead)
        self.logger.info(
            "company=%s score=%d qualified=%s reasons=%s warnings=%s",
            lead.name,
            result.score,
            result.qualified,
            result.reasons,
            result.warnings,
        )
        return result

    def filter_qualified(self, leads: list[CompanyLead]) -> list[CompanyLead]:
        qualified_leads: list[CompanyLead] = []
        for lead in leads:
            result = self.qualify(lead)
            if result.qualified:
                qualified_leads.append(lead)
        return qualified_leads
