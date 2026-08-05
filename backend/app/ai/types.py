from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GeneratedEmail(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    opening: str
    body: str
    cta: str
    signature: str = "{{sender_name}}"
    generation_source: str = "ollama"
    model: str | None = None
    prompt_length: int = 0
    response_time_ms: float = 0.0
    token_estimate: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OllamaGenerateResponse(BaseModel):
    model: str = ""
    response: str = ""
    done: bool = False
    total_duration: int | None = None
    eval_count: int | None = None
