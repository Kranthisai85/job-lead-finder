"""Daily pipeline run log files with retention (Step 38)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger

DAILY_LOG_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})logs\.txt$")
_DAILY_HANDLER_NAME = "lead_finder_daily_run"
_logger = get_logger(__name__)


def daily_log_filename(day: date | None = None) -> str:
    target = day or datetime.now().date()
    return f"{target.isoformat()}logs.txt"


def daily_log_path(*, log_dir: str | Path | None = None, day: date | None = None) -> Path:
    base = Path(log_dir if log_dir is not None else settings.log_dir)
    return base / daily_log_filename(day)


def ensure_log_directory(log_dir: str | Path | None = None) -> Path | None:
    base = Path(log_dir if log_dir is not None else settings.log_dir)
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except OSError as exc:
        _logger.error("daily_log_dir_create_failed path=%s error=%s", base, exc)
        return None


def list_daily_log_files(log_dir: str | Path) -> list[Path]:
    base = Path(log_dir)
    if not base.is_dir():
        return []
    matches: list[tuple[date, Path]] = []
    for path in base.iterdir():
        if not path.is_file():
            continue
        matched = DAILY_LOG_FILENAME_RE.match(path.name)
        if not matched:
            continue
        try:
            file_day = date.fromisoformat(matched.group(1))
        except ValueError:
            continue
        matches.append((file_day, path))
    matches.sort(key=lambda item: item[0])
    return [path for _, path in matches]


def prune_daily_logs(
    log_dir: str | Path,
    *,
    retention_days: int | None = None,
) -> list[Path]:
    """Delete oldest YYYY-MM-DDlogs.txt files beyond retention. Never touch other files."""
    keep = settings.log_retention_days if retention_days is None else retention_days
    keep = max(0, int(keep))
    files = list_daily_log_files(log_dir)
    if keep == 0:
        to_delete = files
    else:
        to_delete = files[:-keep] if len(files) > keep else []
    deleted: list[Path] = []
    for path in to_delete:
        try:
            path.unlink(missing_ok=True)
            deleted.append(path)
            _logger.info("daily_log_pruned file=%s", path.name)
        except OSError as exc:
            _logger.error("daily_log_prune_failed file=%s error=%s", path, exc)
    return deleted


class DailyRunFileHandler(logging.FileHandler):
    """Appends to logs/YYYY-MM-DDlogs.txt using the Step 38 format."""

    def __init__(self, log_dir: str | Path) -> None:
        self._log_dir = Path(log_dir)
        self._current_day = datetime.now().date()
        filename = daily_log_path(log_dir=self._log_dir, day=self._current_day)
        super().__init__(filename, mode="a", encoding="utf-8", delay=True)
        self.set_name(_DAILY_HANDLER_NAME)
        self.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        today = datetime.now().date()
        if today != self._current_day:
            self._current_day = today
            self.close()
            self.baseFilename = str(daily_log_path(log_dir=self._log_dir, day=self._current_day))
            self.stream = self._open()
        super().emit(record)


def attach_daily_run_handler(*, log_dir: str | Path | None = None) -> Path | None:
    """Attach daily file handler to root logger. Returns path or None on failure."""
    base = ensure_log_directory(log_dir)
    if base is None:
        return None
    try:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler.get_name() == _DAILY_HANDLER_NAME:
                root.removeHandler(handler)
                handler.close()
        handler = DailyRunFileHandler(base)
        handler.setLevel(logging.INFO)
        root.addHandler(handler)
        prune_daily_logs(base)
        return daily_log_path(log_dir=base)
    except OSError as exc:
        _logger.error("daily_log_handler_attach_failed error=%s", exc)
        return None


def ensure_daily_run_handler(*, log_dir: str | Path | None = None) -> Path | None:
    """Attach daily handler only if missing (safe during send outside pipeline)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if handler.get_name() == _DAILY_HANDLER_NAME:
            base = Path(log_dir if log_dir is not None else settings.log_dir)
            return daily_log_path(log_dir=base)
    return attach_daily_run_handler(log_dir=log_dir)


def detach_daily_run_handler() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _DAILY_HANDLER_NAME:
            root.removeHandler(handler)
            handler.close()
