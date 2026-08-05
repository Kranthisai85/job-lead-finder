from app.collectors.types import CompanyLead
from app.company_intelligence.models import CompanyIntelligenceReport
from app.contact_discovery.types import ContactDiscoveryReport
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.context import QualificationContext
from app.qualification.engine import QualificationEngine, build_default_engine
from app.qualification.types import QualificationResult
from app.technology.types import TechnologyReport


class QualificationService:
    def __init__(self, engine: QualificationEngine | None = None) -> None:
        self.engine = engine or build_default_engine()
        self.logger = get_logger(__name__)

    def qualify(self, lead: CompanyLead) -> QualificationResult:
        result = self.engine.qualify(lead)
        self._log(lead.name, result)
        return result

    def qualify_enriched(
        self,
        lead: CompanyLead,
        *,
        website_profile: WebsiteProfile | None = None,
        technology_report: TechnologyReport | None = None,
        mobile_report: MobileAppDetectionResult | None = None,
        contacts: ContactDiscoveryReport | None = None,
        hiring_report: HiringDetectionReport | None = None,
        company_intelligence: CompanyIntelligenceReport | None = None,
    ) -> QualificationResult:
        result = self.engine.qualify_enriched(
            lead,
            website_profile=website_profile,
            technology_report=technology_report,
            mobile_report=mobile_report,
            contacts=contacts,
            hiring_report=hiring_report,
            company_intelligence=company_intelligence,
        )
        self._log(lead.name, result)
        return result

    def qualify_context(self, context: QualificationContext) -> QualificationResult:
        result = self.engine.qualify_context(context)
        self._log(context.name, result)
        return result

    def filter_qualified(self, leads: list[CompanyLead]) -> list[CompanyLead]:
        """Return leads that score Good/Excellent. Prefer pipeline enrichment scoring."""
        qualified_leads: list[CompanyLead] = []
        for lead in leads:
            result = self.qualify(lead)
            if result.qualified:
                qualified_leads.append(lead)
        return qualified_leads

    def _log(self, company_name: str, result: QualificationResult) -> None:
        self.logger.info(
            (
                "company=%s qualification_score=%d qualification_level=%s "
                "qualified=%s reasons=%s warnings=%s"
            ),
            company_name,
            result.score,
            result.level.value if hasattr(result.level, "value") else result.level,
            result.qualified,
            result.reasons,
            result.warnings,
        )
