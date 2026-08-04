from app.company_profile.service import CompanyProfileService
from app.contact_discovery.service import ContactDiscoveryService
from app.core.logger import get_logger
from app.crawler.service import WebsiteCrawlerService
from app.email_patterns.service import EmailPatternService
from app.intelligence.service import LeadIntelligenceService
from app.mobile_detection.service import MobileAppDetectionService
from app.pipeline.persistence import PipelinePersistenceService
from app.pipeline.persistence_types import PersistenceResult
from app.pipeline.processor import LeadProcessor
from app.pipeline.types import CompleteLead, ProcessingReport, StartupSeed
from app.qualification.service import QualificationService
from app.technology.service import TechnologyDetectionService


class LeadPipelineService:
    """Public entrypoint for running the complete lead processing pipeline."""

    def __init__(
        self,
        *,
        processor: LeadProcessor | None = None,
        persistence_service: PipelinePersistenceService | None = None,
        crawler_service: WebsiteCrawlerService | None = None,
        company_profile_service: CompanyProfileService | None = None,
        technology_service: TechnologyDetectionService | None = None,
        mobile_service: MobileAppDetectionService | None = None,
        qualification_service: QualificationService | None = None,
        contact_service: ContactDiscoveryService | None = None,
        email_pattern_service: EmailPatternService | None = None,
        intelligence_service: LeadIntelligenceService | None = None,
    ) -> None:
        self.logger = get_logger(__name__)
        self.processor = processor or LeadProcessor(
            crawler_service=crawler_service,
            company_profile_service=company_profile_service,
            technology_service=technology_service,
            mobile_service=mobile_service,
            qualification_service=qualification_service,
            contact_service=contact_service,
            email_pattern_service=email_pattern_service,
            intelligence_service=intelligence_service,
        )
        self.persistence_service = persistence_service

    async def process(self, startup: StartupSeed) -> CompleteLead:
        self.logger.info(
            "service=LeadPipelineService action=process company=%s website=%s",
            startup.name,
            startup.website,
        )
        lead = await self.processor.process(startup)
        self.logger.info(
            (
                "service=LeadPipelineService action=completed company=%s "
                "success=%s errors=%d duration_ms=%.2f"
            ),
            startup.name,
            lead.processing.success,
            len(lead.processing.errors),
            lead.processing.total_duration_ms,
        )
        return lead

    async def process_and_persist(
        self, startup: StartupSeed
    ) -> tuple[CompleteLead, PersistenceResult]:
        lead = await self.process(startup)
        persistence = self.persistence_service or PipelinePersistenceService()
        persist_result = await persistence.persist(lead)
        self.logger.info(
            (
                "service=LeadPipelineService action=process_and_persist "
                "company=%s company_id=%s created=%s updated=%s duration_ms=%.2f"
            ),
            startup.name,
            persist_result.company_id,
            persist_result.company_created,
            persist_result.company_updated,
            persist_result.duration_ms,
        )
        return lead, persist_result

    async def process_with_report(
        self, startup: StartupSeed
    ) -> tuple[CompleteLead, ProcessingReport]:
        lead = await self.process(startup)
        return lead, lead.to_processing_report()
