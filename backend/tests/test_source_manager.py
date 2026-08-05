from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.source_manager.sources  # noqa: F401 — ensure sources are registered
from app.collectors.types import CompanyLead
from app.source_manager.base import BaseSourceCollector
from app.source_manager.manager import StartupSourceManager
from app.source_manager.registry import SourceRegistry
from app.source_manager.service import SourceCollectionService


class StubSourceCollector(BaseSourceCollector):
    def __init__(self, source_name: str, leads: list[CompanyLead] | None = None) -> None:
        self._name = source_name
        self._leads = leads or []

    @property
    def name(self) -> str:
        return self._name

    async def collect_leads(self) -> list[CompanyLead]:
        return list(self._leads)


class FailingSourceCollector(BaseSourceCollector):
    def __init__(self, source_name: str) -> None:
        self._name = source_name

    @property
    def name(self) -> str:
        return self._name

    async def collect_leads(self) -> list[CompanyLead]:
        raise RuntimeError(f"{self._name} failed")


def make_lead(
    name: str,
    website: str,
    source: str = "stub",
) -> CompanyLead:
    return CompanyLead(
        name=name,
        website=website,
        description="Sample description",
        source=source,
        discovered_at=datetime.now(timezone.utc),
    )


class StubRegistry(SourceRegistry):
    _collectors: dict[str, type[BaseSourceCollector]] = {}


@pytest.fixture(autouse=True)
def reset_stub_registry() -> None:
    StubRegistry._collectors = {}


def test_source_registry_register_get_list() -> None:
    assert "producthunt" in SourceRegistry.list()
    assert "hackernews" in SourceRegistry.list()
    assert "github" in SourceRegistry.list()
    assert SourceRegistry.get("producthunt").__name__ == "RegisteredProductHuntSourceCollector"

    with pytest.raises(KeyError):
        SourceRegistry.get("unknown-source")


@pytest.mark.asyncio
async def test_deduplication_by_normalized_website() -> None:
    @StubRegistry.register("alpha")
    class AlphaCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "alpha",
                [
                    make_lead("Acme", "https://www.acme.example", source="alpha"),
                    make_lead("Beta", "https://beta.example", source="alpha"),
                ],
            )

    @StubRegistry.register("beta")
    class BetaCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "beta",
                [
                    make_lead("Acme Duplicate", "https://acme.example", source="beta"),
                ],
            )

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["alpha", "beta"])

    assert report.total_found == 3
    assert report.duplicates_removed == 1
    assert len(report.unique_companies) == 2
    assert {lead.website for lead in report.unique_companies} == {
        "acme.example",
        "beta.example",
    }


@pytest.mark.asyncio
async def test_execution_order_is_sequential() -> None:
    order: list[str] = []

    @StubRegistry.register("first")
    class FirstCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__("first")

        async def collect_leads(self) -> list[CompanyLead]:
            order.append("first")
            return [make_lead("First", "https://first.example", source="first")]

    @StubRegistry.register("second")
    class SecondCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__("second")

        async def collect_leads(self) -> list[CompanyLead]:
            order.append("second")
            return [make_lead("Second", "https://second.example", source="second")]

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["first", "second"])

    assert order == ["first", "second"]
    assert report.collectors_run == ["first", "second"]


@pytest.mark.asyncio
async def test_statistics_and_executions() -> None:
    @StubRegistry.register("stats")
    class StatsCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "stats",
                [make_lead("Stats Co", "https://stats.example", source="stats")],
            )

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["stats"])

    assert len(report.collector_statistics) == 1
    assert report.collector_statistics[0].collector_name == "stats"
    assert report.collector_statistics[0].companies_collected == 1
    assert report.collector_statistics[0].success is True

    assert len(report.collector_executions) == 1
    assert report.collector_executions[0].collector_name == "stats"
    assert report.collector_executions[0].success is True
    assert report.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_empty_collectors() -> None:
    @StubRegistry.register("empty")
    class EmptyCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__("empty", [])

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["empty"])

    assert report.total_found == 0
    assert report.duplicates_removed == 0
    assert report.unique_companies == []
    assert report.collector_statistics[0].companies_collected == 0
    assert report.collector_statistics[0].success is True


@pytest.mark.asyncio
async def test_collector_failures_continue() -> None:
    @StubRegistry.register("good")
    class GoodCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "good",
                [make_lead("Good", "https://good.example", source="good")],
            )

    @StubRegistry.register("bad")
    class BadCollector(FailingSourceCollector):
        def __init__(self) -> None:
            super().__init__("bad")

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["bad", "good"])

    assert len(report.unique_companies) == 1
    assert report.unique_companies[0].name == "Good"
    assert report.collector_statistics[0].success is False
    assert report.collector_statistics[0].error == "bad failed"
    assert report.collector_statistics[1].success is True


@pytest.mark.asyncio
async def test_partial_success() -> None:
    @StubRegistry.register("one")
    class OneCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "one",
                [make_lead("One", "https://one.example", source="one")],
            )

    @StubRegistry.register("two")
    class TwoCollector(FailingSourceCollector):
        def __init__(self) -> None:
            super().__init__("two")

    manager = StartupSourceManager(registry=StubRegistry)
    report = await manager.collect(["one", "two"])

    assert report.total_found == 1
    assert len(report.unique_companies) == 1
    assert any(stat.success for stat in report.collector_statistics)
    assert any(not stat.success for stat in report.collector_statistics)


@pytest.mark.asyncio
async def test_service_collect_with_explicit_sources() -> None:
    @StubRegistry.register("svc")
    class ServiceCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "svc",
                [make_lead("Service Co", "https://service.example", source="svc")],
            )

    service = SourceCollectionService(manager=StartupSourceManager(registry=StubRegistry))
    report = await service.collect(["svc"])

    assert len(report.unique_companies) == 1
    assert report.unique_companies[0].name == "Service Co"


@pytest.mark.asyncio
async def test_service_collect_all_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    @StubRegistry.register("cfg")
    class ConfigCollector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "cfg",
                [make_lead("Config Co", "https://config.example", source="cfg")],
            )

    monkeypatch.setattr(
        "app.source_manager.service.settings.enabled_sources",
        "cfg",
    )
    service = SourceCollectionService(manager=StartupSourceManager(registry=StubRegistry))
    report = await service.collect_all()

    assert report.collectors_run == ["cfg"]
    assert len(report.unique_companies) == 1


@pytest.mark.asyncio
async def test_max_collectors_limit() -> None:
    @StubRegistry.register("src0")
    class Src0Collector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "src0",
                [make_lead("Co 0", "https://co0.example", source="src0")],
            )

    @StubRegistry.register("src1")
    class Src1Collector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "src1",
                [make_lead("Co 1", "https://co1.example", source="src1")],
            )

    @StubRegistry.register("src2")
    class Src2Collector(StubSourceCollector):
        def __init__(self) -> None:
            super().__init__(
                "src2",
                [make_lead("Co 2", "https://co2.example", source="src2")],
            )

    manager = StartupSourceManager(registry=StubRegistry, max_collectors=2)
    report = await manager.collect(["src0", "src1", "src2"])

    assert report.collectors_run == ["src0", "src1"]
    assert len(report.unique_companies) == 2
