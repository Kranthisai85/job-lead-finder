from datetime import datetime

from app.contact_discovery.types import ContactDiscoveryReport
from app.core.timezone import now_app
from app.crawler.types import WebsiteProfile
from app.intelligence.types import PIPELINE_VERSION, LeadIntelligence, LeadIntelligenceMetadata
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import TechnologyReport


class LeadIntelligenceBuilder:
    def __init__(self) -> None:
        self._company: CompanyResponse | None = None
        self._website_profile: WebsiteProfile | None = None
        self._technology_report: TechnologyReport | None = None
        self._mobile_detection: MobileAppDetectionResult | None = None
        self._contact_discovery: ContactDiscoveryReport | None = None
        self._qualification: QualificationResult | None = None
        self._collector_name: str | None = None
        self._processing_time_ms: float = 0.0
        self._pipeline_version: str = PIPELINE_VERSION
        self._created_at: datetime = now_app()

    def with_company(self, company: CompanyResponse) -> "LeadIntelligenceBuilder":
        self._company = company
        return self

    def with_website_profile(self, profile: WebsiteProfile) -> "LeadIntelligenceBuilder":
        self._website_profile = profile
        return self

    def with_technology_report(self, report: TechnologyReport) -> "LeadIntelligenceBuilder":
        self._technology_report = report
        return self

    def with_mobile_detection(self, result: MobileAppDetectionResult) -> "LeadIntelligenceBuilder":
        self._mobile_detection = result
        return self

    def with_contact_discovery(self, report: ContactDiscoveryReport) -> "LeadIntelligenceBuilder":
        self._contact_discovery = report
        return self

    def with_qualification(self, result: QualificationResult) -> "LeadIntelligenceBuilder":
        self._qualification = result
        return self

    def with_collector_name(self, collector_name: str | None) -> "LeadIntelligenceBuilder":
        self._collector_name = collector_name
        return self

    def with_processing_time_ms(self, processing_time_ms: float) -> "LeadIntelligenceBuilder":
        self._processing_time_ms = processing_time_ms
        return self

    def with_pipeline_version(self, pipeline_version: str) -> "LeadIntelligenceBuilder":
        self._pipeline_version = pipeline_version
        return self

    def with_created_at(self, created_at: datetime) -> "LeadIntelligenceBuilder":
        self._created_at = created_at
        return self

    def build(self) -> LeadIntelligence:
        if self._company is None:
            raise ValueError("company is required to build LeadIntelligence")

        metadata = LeadIntelligenceMetadata(
            created_at=self._created_at,
            pipeline_version=self._pipeline_version,
            collector_name=self._collector_name,
            processing_time_ms=self._processing_time_ms,
        )
        return LeadIntelligence(
            company=self._company,
            website_profile=self._website_profile,
            technology_report=self._technology_report,
            mobile_detection=self._mobile_detection,
            contact_discovery=self._contact_discovery,
            qualification=self._qualification,
            metadata=metadata,
        )
