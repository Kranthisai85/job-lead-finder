from pydantic import BaseModel, Field


class Technology(BaseModel):
    name: str
    category: str
    confidence: int = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)


class RuleMatch(BaseModel):
    matched: bool
    confidence: int = Field(default=0, ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)


class TechnologyReport(BaseModel):
    url: str
    technologies: list[Technology] = Field(default_factory=list)
    detected_count: int = 0
