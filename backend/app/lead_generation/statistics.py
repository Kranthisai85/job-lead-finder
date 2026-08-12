from __future__ import annotations

from collections import Counter

from app.lead_generation.types import (
    LeadGenerationReport,
    LeadGenerationResult,
    LeadGenerationStatistics,
)


def _classify_skip(result: LeadGenerationResult) -> str | None:
    if result.queued:
        return None
    blob = " ".join(result.warnings).lower()
    if "duplicate" in blob:
        return "duplicate"
    if "no contact email" in blob or "no_recipient" in blob:
        return "no_recipient"
    if "no mail (mx)" in blob or "no_mx" in blob:
        return "no_mx"
    if "mailbox rejected" in blob or "mailbox_rejected" in blob:
        return "mailbox_rejected"
    if "below min_lead_score" in blob or "below_min_score" in blob:
        return "low_score"
    if result.warnings:
        return "other_skip"
    return None


def build_statistics(
    results: list[LeadGenerationResult],
    *,
    total_collected: int,
    duration_ms: float,
) -> LeadGenerationStatistics:
    processed = len(results)
    persisted = sum(1 for item in results if item.persisted)
    qualified = sum(1 for item in results if item.qualified)
    emails_generated = sum(1 for item in results if item.email_generated)
    queued = sum(1 for item in results if item.queued)
    failed = sum(1 for item in results if not item.success)

    skip_counts: Counter[str] = Counter()
    for item in results:
        reason = _classify_skip(item)
        if reason:
            skip_counts[reason] += 1

    return LeadGenerationStatistics(
        total_collected=total_collected,
        processed=processed,
        persisted=persisted,
        qualified=qualified,
        emails_generated=emails_generated,
        queued=queued,
        failed=failed,
        skipped_duplicate=skip_counts.get("duplicate", 0),
        skipped_no_recipient=skip_counts.get("no_recipient", 0),
        skipped_no_mx=skip_counts.get("no_mx", 0),
        skipped_mailbox_rejected=skip_counts.get("mailbox_rejected", 0),
        skipped_low_score=skip_counts.get("low_score", 0),
        duration_ms=round(duration_ms, 2),
        skip_reasons=dict(skip_counts),
    )


def finalize_report(report: LeadGenerationReport) -> LeadGenerationReport:
    report.statistics = build_statistics(
        report.results,
        total_collected=report.statistics.total_collected,
        duration_ms=report.statistics.duration_ms,
    )
    report.success = report.statistics.failed == 0 and not report.errors
    return report
