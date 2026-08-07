"""Daily run logging and retention tests (Step 38)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core import daily_logging
from app.core.config import settings
from app.core.daily_logging import (
    attach_daily_run_handler,
    daily_log_filename,
    daily_log_path,
    detach_daily_run_handler,
    ensure_log_directory,
    list_daily_log_files,
    prune_daily_logs,
)
from app.lead_generation.service import LeadGenerationService
from app.source_manager.types import SourceCollectionReport
from tests.test_lead_generation import build_orchestrator


def test_daily_log_filename_format() -> None:
    assert daily_log_filename(date(2026, 8, 9)) == "2026-08-09logs.txt"


def test_log_directory_is_created(tmp_path: Path) -> None:
    target = tmp_path / "pipeline-logs"
    created = ensure_log_directory(target)
    assert created == target
    assert target.is_dir()


def test_retention_keeps_newest_seven_and_deletes_oldest(tmp_path: Path) -> None:
    start = date(2026, 8, 1)
    for offset in range(8):
        day = start + timedelta(days=offset)
        (tmp_path / daily_log_filename(day)).write_text(f"day {day}\n", encoding="utf-8")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep me\n", encoding="utf-8")
    outside = tmp_path.parent / "outside-2026-08-01logs.txt"
    outside.write_text("untouched\n", encoding="utf-8")

    deleted = prune_daily_logs(tmp_path, retention_days=7)
    remaining = list_daily_log_files(tmp_path)

    assert len(deleted) == 1
    assert deleted[0].name == "2026-08-01logs.txt"
    assert len(remaining) == 7
    assert remaining[0].name == "2026-08-02logs.txt"
    assert remaining[-1].name == "2026-08-08logs.txt"
    assert unrelated.exists()
    assert outside.exists()


def test_retention_respects_log_retention_days_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_retention_days", 3)
    start = date(2026, 8, 1)
    for offset in range(5):
        day = start + timedelta(days=offset)
        (tmp_path / daily_log_filename(day)).write_text("x\n", encoding="utf-8")

    prune_daily_logs(tmp_path)
    remaining = [path.name for path in list_daily_log_files(tmp_path)]
    assert remaining == [
        "2026-08-03logs.txt",
        "2026-08-04logs.txt",
        "2026-08-05logs.txt",
    ]


def test_unrelated_txt_not_deleted(tmp_path: Path) -> None:
    (tmp_path / "2026-08-09logs.txt").write_text("a\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("docs\n", encoding="utf-8")
    (tmp_path / "app.log").write_text("rotating\n", encoding="utf-8")
    prune_daily_logs(tmp_path, retention_days=1)
    assert (tmp_path / "readme.txt").exists()
    assert (tmp_path / "app.log").exists()
    assert (tmp_path / "2026-08-09logs.txt").exists()


@pytest.mark.asyncio
async def test_pipeline_writes_daily_log_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    # Reset logging configuration so handlers can attach to the temp dir.
    import app.core.logger as logger_module

    monkeypatch.setattr(logger_module, "_LOGGING_CONFIGURED", False)
    detach_daily_run_handler()

    harness = build_orchestrator()
    collection = AsyncMock(return_value=SourceCollectionReport(unique_companies=[]))
    harness.orchestrator.collection_service.collect_all = collection

    service = LeadGenerationService(orchestrator=harness.orchestrator)
    report = await service.run(persist=False, generate_emails=False, enqueue_emails=False)
    assert report.statistics.total_collected == 0

    log_file = daily_log_path(log_dir=tmp_path)
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "[PIPELINE]" in content or "LeadGenerationService" in content
    assert "completed" in content.lower() or "Completed" in content
    detach_daily_run_handler()


@pytest.mark.asyncio
async def test_logging_failure_does_not_crash_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "missing" / "nested"))

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(daily_logging, "attach_daily_run_handler", boom)

    harness = build_orchestrator()
    harness.orchestrator.collection_service.collect_all = AsyncMock(
        return_value=SourceCollectionReport(unique_companies=[])
    )
    service = LeadGenerationService(orchestrator=harness.orchestrator)
    report = await service.run(persist=False, generate_emails=False, enqueue_emails=False)
    assert report is not None


def test_attach_writes_stage_style_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    detach_daily_run_handler()
    path = attach_daily_run_handler(log_dir=tmp_path)
    assert path is not None
    logging.getLogger("app.test.daily").info("[PIPELINE] Starting lead generation run")
    logging.getLogger("app.test.daily").info(
        "[QUALIFICATION] company=Example score=72 status=MEDIUM eligible=true"
    )
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = path.read_text(encoding="utf-8")
    assert "[PIPELINE] Starting lead generation run" in content
    assert "[QUALIFICATION] company=Example" in content
    detach_daily_run_handler()
