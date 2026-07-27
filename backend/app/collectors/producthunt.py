from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead


@CollectorRegistry.register("producthunt")
class ProductHuntCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "producthunt"

    async def collect(self) -> list[Any]:
        return []

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        _ = raw_items
        return []
