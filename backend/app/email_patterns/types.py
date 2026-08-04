from pydantic import BaseModel, ConfigDict, Field, computed_field


class EmailPattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern_name: str
    template: str
    confidence: float = Field(ge=0.0, le=1.0)
    generated_addresses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class EmailPatternReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: str
    patterns: list[EmailPattern] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    inferred_pattern: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unique_candidates(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for address in self.candidates:
            normalized = address.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
        return ordered

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_candidate(self) -> str | None:
        if not self.patterns:
            return None
        top_pattern = max(self.patterns, key=lambda pattern: pattern.confidence)
        if top_pattern.generated_addresses:
            return top_pattern.generated_addresses[0].lower()
        if self.unique_candidates:
            return self.unique_candidates[0]
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_email(self) -> str | None:
        return self.best_candidate
