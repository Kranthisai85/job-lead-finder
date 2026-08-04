from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.email_patterns.types import EmailPatternReport
from app.intelligence.types import LeadIntelligence
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.technology.types import TechnologyReport

PIPELINE_VERSION = "1.0.0"


class StartupSeed(BaseModel):
    name: str
    website: str
    description: str | None = None
    source: str = "manual"


class StageTiming(BaseModel):
    stage: str
    duration_ms: float
    success: bool = True
    error: str | None = None


class ProcessingMetadata(BaseModel):
    pipeline_version: str = PIPELINE_VERSION
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    total_duration_ms: float = 0.0
    stage_timings: list[StageTiming] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = False


class ProcessingReport(BaseModel):
    total_duration_ms: float = 0.0
    stage_durations: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = False


class CompleteLead(BaseModel):
    startup: StartupSeed
    website_profile: WebsiteProfile | None = None
    company_profile: CompanyProfile | None = None
    technology_report: TechnologyReport | None = None
    mobile_report: MobileAppDetectionResult | None = None
    qualification_report: QualificationResult | None = None
    contacts: ContactDiscoveryReport | None = None
    email_pattern_report: EmailPatternReport | None = None
    lead_intelligence: LeadIntelligence | None = None
    processing: ProcessingMetadata = Field(default_factory=ProcessingMetadata)

    def to_processing_report(self) -> ProcessingReport:
        return ProcessingReport(
            total_duration_ms=self.processing.total_duration_ms,
            stage_durations={
                timing.stage: timing.duration_ms for timing in self.processing.stage_timings
            },
            warnings=list(self.processing.warnings),
            errors=list(self.processing.errors),
            success=self.processing.success,
        )
