from enum import Enum

from pydantic import BaseModel, Field, computed_field


class QualificationLevel(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"


class RuleEvaluation(BaseModel):
    points: int = 0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking: bool = False


class QualificationResult(BaseModel):
    qualified: bool
    score: int
    level: QualificationLevel = QualificationLevel.POOR
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualification_score(self) -> int:
        return self.score

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualification_level(self) -> str:
        return self.level.value if isinstance(self.level, QualificationLevel) else str(self.level)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualification_reasons(self) -> list[str]:
        return list(self.reasons)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualification_warnings(self) -> list[str]:
        return list(self.warnings)
