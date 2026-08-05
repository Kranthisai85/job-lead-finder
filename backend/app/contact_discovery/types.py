from enum import Enum

from pydantic import BaseModel, Field, computed_field


class DiscoverySource(str, Enum):
    HTML = "html"
    JSON_LD = "json_ld"
    EMAIL = "email"
    SOCIAL = "social"
    TEAM_PAGE = "team_page"
    ABOUT_PAGE = "about_page"
    CONTACT_PAGE = "contact_page"
    CAREERS_PAGE = "careers_page"
    MERGED = "merged"


class ContactCandidate(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    role: str | None = None
    company_role: str | None = None
    linkedin: str | None = None
    github: str | None = None
    twitter: str | None = None
    source_page: str | None = None
    discovery_source: str | None = None
    contact_score: int = Field(default=0, ge=0, le=100)
    contact_priority: int = Field(default=99, ge=1, le=99)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_name(self) -> str | None:
        if self.full_name and self.full_name.strip():
            return self.full_name.strip()
        parts = [self.first_name or "", self.last_name or ""]
        joined = " ".join(part for part in parts if part).strip()
        return joined or None


class CompanyDecisionMaker(BaseModel):
    """DTO for ranked decision makers (also mirrored in Mongo)."""

    name: str
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    github: str | None = None
    twitter: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_page: str | None = None
    contact_score: int = Field(default=0, ge=0, le=100)
    discovery_source: str | None = None
    contact_priority: int = Field(default=99, ge=1, le=99)


class ContactDiscoveryReport(BaseModel):
    url: str
    contacts: list[ContactCandidate] = Field(default_factory=list)
    decision_makers: list[CompanyDecisionMaker] = Field(default_factory=list)
    generic_contacts: list[ContactCandidate] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    linkedin_profiles: list[str] = Field(default_factory=list)
    twitter_profiles: list[str] = Field(default_factory=list)
    github_profiles: list[str] = Field(default_factory=list)
    contact_count: int = 0
    decision_makers_found: int = 0
    generic_contacts_found: int = 0
    best_contact: ContactCandidate | None = None
    best_contact_score: int | None = None
    pages_scanned: list[str] = Field(default_factory=list)
