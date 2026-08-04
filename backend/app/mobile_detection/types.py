from pydantic import BaseModel, Field


class RuleMatch(BaseModel):
    matched: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    detected_links: list[str] = Field(default_factory=list)
    android: bool = False
    ios: bool = False


class MobileAppDetectionResult(BaseModel):
    has_mobile_app: bool
    confidence: float = Field(ge=0.0, le=1.0)
    android_detected: bool = False
    ios_detected: bool = False
    evidence: list[str] = Field(default_factory=list)
    detected_links: list[str] = Field(default_factory=list)
