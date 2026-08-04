from pydantic import BaseModel, Field


class ContactCandidate(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    role: str | None = None
    linkedin: str | None = None
    twitter: str | None = None
    source_page: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContactDiscoveryReport(BaseModel):
    url: str
    contacts: list[ContactCandidate] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    linkedin_profiles: list[str] = Field(default_factory=list)
    twitter_profiles: list[str] = Field(default_factory=list)
    github_profiles: list[str] = Field(default_factory=list)
    contact_count: int = 0
