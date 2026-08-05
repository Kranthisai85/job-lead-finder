from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonalizedEmailContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str
    company_summary: str
    personalized_opening: str
    mobile_app_opportunity: str
    technologies_summary: str
    qualification_summary: str
    suggested_value_proposition: str
    cta_recommendation: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    is_flutter_lead: bool = False
    has_mobile_app: bool = False
    technology_names: list[str] = Field(default_factory=list)
