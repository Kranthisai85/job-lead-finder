from datetime import datetime

from app.contact_discovery.types import ContactDiscoveryReport
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.intelligence.builder import LeadIntelligenceBuilder
from app.intelligence.types import LeadIntelligence
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import TechnologyReport


class LeadIntelligenceService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def build(
        self,
        *,
        company: CompanyResponse,
        website_profile: WebsiteProfile | None = None,
        technology_report: TechnologyReport | None = None,
        mobile_detection: MobileAppDetectionResult | None = None,
        contact_discovery: ContactDiscoveryReport | None = None,
        qualification: QualificationResult | None = None,
        collector_name: str | None = None,
        processing_time_ms: float = 0.0,
        pipeline_version: str | None = None,
        created_at: datetime | None = None,
    ) -> LeadIntelligence:
        builder = (
            LeadIntelligenceBuilder()
            .with_company(company)
            .with_collector_name(collector_name)
            .with_processing_time_ms(processing_time_ms)
        )

        if website_profile is not None:
            builder.with_website_profile(website_profile)
        if technology_report is not None:
            builder.with_technology_report(technology_report)
        if mobile_detection is not None:
            builder.with_mobile_detection(mobile_detection)
        if contact_discovery is not None:
            builder.with_contact_discovery(contact_discovery)
        if qualification is not None:
            builder.with_qualification(qualification)
        if pipeline_version is not None:
            builder.with_pipeline_version(pipeline_version)
        if created_at is not None:
            builder.with_created_at(created_at)

        intelligence = builder.build()
        self.logger.info(
            (
                "company=%s is_good_lead=%s qualification_score=%d "
                "has_mobile_app=%s technology_count=%d contact_count=%d"
            ),
            intelligence.company.name,
            intelligence.is_good_lead,
            intelligence.qualification_score,
            intelligence.has_mobile_app,
            len(intelligence.technology_names),
            (intelligence.contact_discovery.contact_count if intelligence.contact_discovery else 0),
        )
        return intelligence
