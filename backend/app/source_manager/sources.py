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


class CollectorBackedSource(BaseSourceCollector):
    """Adapter from CollectorRegistry collectors → source manager leads."""

    def __init__(self, source_name: str, collector: BaseCollector | None = None) -> None:
        self._name = source_name
        self._collector = collector

    @property
    def name(self) -> str:
        return self._name

    async def collect_leads(self) -> list[CompanyLead]:
        collector = self._collector or self._build_default_collector()
        raw_items = await collector.collect()
        normalized = await collector.normalize(raw_items)
        return await collector.validate(normalized)

    def _build_default_collector(self) -> BaseCollector:
        from app.collectors.factory import CollectorFactory

        company_service = CompanyService(CompanyRepository())
        return CollectorFactory.create(self._name, company_service)


@SourceRegistry.register("producthunt")
class RegisteredProductHuntSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("producthunt", collector=collector)


@SourceRegistry.register("hackernews")
class RegisteredHackerNewsSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("hackernews", collector=collector)


@SourceRegistry.register("ycombinator")
class RegisteredYCombinatorSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("ycombinator", collector=collector)


@SourceRegistry.register("github")
class RegisteredGitHubSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("github", collector=collector)


@SourceRegistry.register("rss")
class RegisteredRssSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("rss", collector=collector)


@SourceRegistry.register("googlenews")
class RegisteredGoogleNewsSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("googlenews", collector=collector)


@SourceRegistry.register("reddit")
class RegisteredRedditSourceCollector(CollectorBackedSource):
    def __init__(self, collector: BaseCollector | None = None) -> None:
        super().__init__("reddit", collector=collector)


_register_placeholder("betalist")
_register_placeholder("indiehackers")
