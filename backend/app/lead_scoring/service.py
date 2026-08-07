"""Thin scoring service — no database writes."""

from __future__ import annotations

from app.core.config import settings
from app.lead_scoring.scorer import is_queue_eligible, score_lead
from app.lead_scoring.signals import extract_signals
from app.lead_scoring.types import LeadScoreResult, LeadScoreSignals
from app.pipeline.types import CompleteLead


class LeadScoringService:
    """Deterministic outbound lead scoring."""

    def __init__(self, *, min_lead_score: int | None = None) -> None:
        self.min_lead_score = settings.min_lead_score if min_lead_score is None else min_lead_score

    def score(self, lead: CompleteLead) -> LeadScoreResult:
        return score_lead(extract_signals(lead))

    def score_signals(self, signals: LeadScoreSignals) -> LeadScoreResult:
        return score_lead(signals)

    def is_eligible(self, result: LeadScoreResult) -> bool:
        return is_queue_eligible(result.score, min_lead_score=self.min_lead_score)
