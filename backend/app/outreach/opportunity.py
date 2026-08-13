"""Outbound opportunity signals — job (hiring) vs freelance (mobile build)."""

from __future__ import annotations

from enum import Enum

from app.pipeline.types import CompleteLead


class OutreachMode(str, Enum):
    HIRING = "hiring"  # company is hiring mobile/Flutter/engineering
    FREELANCE = "freelance"  # product exists but weak/no mobile — contract angle
    NONE = "none"


def classify_outreach_mode(lead: CompleteLead) -> OutreachMode:
    """Pick the best outreach angle for this lead (or none)."""
    hiring = lead.hiring_report
    if hiring is not None:
        if hiring.flutter_jobs > 0 or hiring.mobile_jobs > 0:
            return OutreachMode.HIRING
        if hiring.jobs_found > 0 and (
            hiring.has_engineering_careers_page or hiring.engineering_jobs > 0
        ):
            return OutreachMode.HIRING

    has_mobile = False
    if lead.mobile_report is not None:
        has_mobile = bool(lead.mobile_report.has_mobile_app)
    elif lead.lead_intelligence is not None:
        has_mobile = bool(lead.lead_intelligence.has_mobile_app)

    # Freelance / contract: web product with no (or weak) mobile presence.
    if not has_mobile:
        return OutreachMode.FREELANCE

    return OutreachMode.NONE


def has_opportunity_signal(lead: CompleteLead) -> bool:
    return classify_outreach_mode(lead) != OutreachMode.NONE


def hiring_roles_summary(lead: CompleteLead, *, limit: int = 3) -> str:
    hiring = lead.hiring_report
    if hiring is None or not hiring.opportunities:
        if hiring and (hiring.flutter_jobs or hiring.mobile_jobs or hiring.jobs_found):
            parts: list[str] = []
            if hiring.flutter_jobs:
                parts.append(f"{hiring.flutter_jobs} Flutter role(s)")
            if hiring.mobile_jobs:
                parts.append(f"{hiring.mobile_jobs} mobile role(s)")
            if hiring.jobs_found and not parts:
                parts.append(f"{hiring.jobs_found} open role(s)")
            return "; ".join(parts)
        return "No public job titles detected"
    titles: list[str] = []
    for opportunity in hiring.opportunities:
        title = (opportunity.title or "").strip()
        if not title:
            continue
        titles.append(title)
        if len(titles) >= limit:
            break
    return "; ".join(titles) if titles else "Open engineering roles listed"
