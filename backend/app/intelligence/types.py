from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import TechnologyReport

PIPELINE_VERSION = "1.0.0"

FOUNDER_ROLES = {"founder", "co-founder", "ceo", "owner"}


class LeadIntelligenceMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_version: str = PIPELINE_VERSION
    collector_name: str | None = None
    processing_time_ms: float = 0.0


class LeadIntelligence(BaseModel):
    model_config = ConfigDict(frozen=True)

    company: CompanyResponse
    website_profile: WebsiteProfile | None = None
    technology_report: TechnologyReport | None = None
    mobile_detection: MobileAppDetectionResult | None = None
    contact_discovery: ContactDiscoveryReport | None = None
    qualification: QualificationResult | None = None
    metadata: LeadIntelligenceMetadata

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_mobile_app(self) -> bool:
        if self.mobile_detection is None:
            return False
        return self.mobile_detection.has_mobile_app

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_contact(self) -> ContactCandidate | None:
        if self.contact_discovery is None:
            return None
        if self.contact_discovery.best_contact is not None:
            return self.contact_discovery.best_contact
        if not self.contact_discovery.contacts:
            return None
        return max(
            self.contact_discovery.contacts,
            key=lambda contact: (contact.contact_score, contact.confidence),
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_email(self) -> str | None:
        best = self.best_contact
        if best and best.email:
            return best.email
        if self.contact_discovery and self.contact_discovery.emails:
            return self.contact_discovery.emails[0]
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_founder(self) -> ContactCandidate | None:
        if self.contact_discovery is None:
            return None
        founders = [
            contact
            for contact in self.contact_discovery.contacts
            if contact.role and contact.role.lower() in FOUNDER_ROLES
        ]
        if not founders:
            return None
        return max(founders, key=lambda contact: contact.confidence)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def technology_names(self) -> list[str]:
        if self.technology_report is None:
            return []
        return [technology.name for technology in self.technology_report.technologies]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualification_score(self) -> int:
        if self.qualification is None:
            return 0
        return self.qualification.score

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_good_lead(self) -> bool:
        """True when the scoring engine marks the lead Good or Excellent."""
        return bool(self.qualification and self.qualification.qualified)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
