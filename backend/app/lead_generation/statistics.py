from __future__ import annotations

from app.lead_generation.types import (
    LeadGenerationReport,
    LeadGenerationResult,
    LeadGenerationStatistics,
)


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

    return LeadGenerationStatistics(
        total_collected=total_collected,
        processed=processed,
        persisted=persisted,
        qualified=qualified,
        emails_generated=emails_generated,
        queued=queued,
        failed=failed,
        duration_ms=round(duration_ms, 2),
    )


def finalize_report(report: LeadGenerationReport) -> LeadGenerationReport:
    report.statistics = build_statistics(
        report.results,
        total_collected=report.statistics.total_collected,
        duration_ms=report.statistics.duration_ms,
    )
    report.success = report.statistics.failed == 0 and not report.errors
    return report
