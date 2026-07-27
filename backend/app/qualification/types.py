from pydantic import BaseModel, Field


class RuleEvaluation(BaseModel):
    points: int = 0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking: bool = False


class QualificationResult(BaseModel):
    qualified: bool
    score: int
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
