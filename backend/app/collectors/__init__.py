"""Source collector framework."""

from app.collectors import github  # noqa: F401 — registers collectors
from app.collectors import googlenews  # noqa: F401 — registers collectors
from app.collectors import hackernews  # noqa: F401 — registers collectors
from app.collectors import producthunt  # noqa: F401 — registers collectors
from app.collectors import reddit  # noqa: F401 — registers collectors
from app.collectors import rss  # noqa: F401 — registers collectors
from app.collectors import ycombinator  # noqa: F401 — registers collectors
from app.collectors.base import BaseCollector
from app.collectors.factory import CollectorFactory
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CollectorRunResult, CompanyLead

__all__ = [
    "BaseCollector",
    "CollectorFactory",
    "CollectorRegistry",
    "CollectorRunResult",
    "CompanyLead",
]
