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


def format_run_summary(
    stats: LeadGenerationStatistics,
    *,
    total_found: int = 0,
    unique_companies: int = 0,
    duplicates_removed: int = 0,
    personalized: int = 0,
    success: bool = True,
) -> str:
    """Human-readable end-of-run summary for daily logs and Run Now."""
    other_skips = stats.skip_reasons.get("other_skip", 0)
    status = "SUCCESS" if success else "FAILED"
    lines = [
        "[RUN SUMMARY] ========== Lead generation run ==========",
        f"[RUN SUMMARY] Fetched (raw from sources):     {total_found}",
        (
            f"[RUN SUMMARY] Unique after dedupe:           {unique_companies} "
            f"(duplicates removed: {duplicates_removed})"
        ),
        f"[RUN SUMMARY] Selected for pipeline:          {stats.total_collected}",
        f"[RUN SUMMARY] Processed:                      {stats.processed}",
        f"[RUN SUMMARY] Saved to DB (companies):         {stats.persisted}",
        f"[RUN SUMMARY] Qualified:                      {stats.qualified}",
        f"[RUN SUMMARY] Personalized:                   {personalized}",
        f"[RUN SUMMARY] Emails generated:               {stats.emails_generated}",
        f"[RUN SUMMARY] Shortlisted / queued:           {stats.queued}",
        f"[RUN SUMMARY] Failed:                         {stats.failed}",
        f"[RUN SUMMARY] Skipped — duplicate:            {stats.skipped_duplicate}",
        f"[RUN SUMMARY] Skipped — no recipient email:   {stats.skipped_no_recipient}",
        f"[RUN SUMMARY] Skipped — no MX:                {stats.skipped_no_mx}",
        f"[RUN SUMMARY] Skipped — mailbox rejected:     {stats.skipped_mailbox_rejected}",
        f"[RUN SUMMARY] Skipped — low score:            {stats.skipped_low_score}",
        f"[RUN SUMMARY] Skipped — other:                {other_skips}",
        f"[RUN SUMMARY] Duration:                       {stats.duration_ms:.0f} ms",
        f"[RUN SUMMARY] Status:                         {status}",
        "[RUN SUMMARY] ========================================",
    ]
    return "\n".join(lines)
