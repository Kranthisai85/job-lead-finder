from datetime import datetime
from enum import Enum

from pymongo import IndexModel

from app.models.base import BaseDocument


class ScraperJobType(str, Enum):
    DISCOVERY = "discovery"
    CRAWL = "crawl"
    ENRICHMENT = "enrichment"
    OUTREACH = "outreach"


class ScraperJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ScraperJob(BaseDocument):
    job_type: ScraperJobType
    status: ScraperJobStatus = ScraperJobStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    class Settings:
        name = "scraper_jobs"
        indexes = [
            IndexModel([("job_type", 1), ("status", 1)]),
            IndexModel([("status", 1), ("created_at", -1)]),
            IndexModel([("created_at", -1)]),
        ]
