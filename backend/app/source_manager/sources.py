from __future__ import annotations

from app.collectors.base import BaseCollector
from app.collectors.types import CompanyLead
from app.repositories.company_repository import CompanyRepository
from app.services.company_service import CompanyService
from app.source_manager.base import BaseSourceCollector
from app.source_manager.registry import SourceRegistry


class PlaceholderSourceCollector(BaseSourceCollector):
    """Deterministic placeholder until a real collector is implemented."""

    def __init__(self, source_name: str) -> None:
        self._name = source_name

    @property
    def name(self) -> str:
        return self._name

    async def collect_leads(self) -> list[CompanyLead]:
        return []


def _register_placeholder(name: str) -> type[BaseSourceCollector]:
    @SourceRegistry.register(name)
    class _Placeholder(PlaceholderSourceCollector):
        def __init__(self) -> None:
            super().__init__(name)

    return _Placeholder


class ProductHuntSourceCollector(BaseSourceCollector):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        self._collector = collector

    @property
    def name(self) -> str:
        return "producthunt"

    async def collect_leads(self) -> list[CompanyLead]:
        collector = self._collector or self._build_default_collector()
        raw_items = await collector.collect()
        normalized = await collector.normalize(raw_items)
        return await collector.validate(normalized)

    @staticmethod
    def _build_default_collector() -> BaseCollector:
        from app.collectors.factory import CollectorFactory

        company_service = CompanyService(CompanyRepository())
        return CollectorFactory.create("producthunt", company_service)


@SourceRegistry.register("producthunt")
class RegisteredProductHuntSourceCollector(ProductHuntSourceCollector):
    pass


_register_placeholder("hackernews")
_register_placeholder("betalist")
_register_placeholder("ycombinator")
_register_placeholder("github")
_register_placeholder("reddit")
_register_placeholder("rss")
_register_placeholder("googlenews")
_register_placeholder("indiehackers")
