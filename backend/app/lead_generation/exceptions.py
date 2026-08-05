from __future__ import annotations


class LeadGenerationError(Exception):
    """Base error for lead generation orchestration."""


class LeadGenerationStageError(LeadGenerationError):
    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage}: {message}")
