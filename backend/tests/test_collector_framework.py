from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import app.collectors  # noqa: F401 — ensure collectors are registered
from app.collectors.base import BaseCollector
from app.collectors.factory import CollectorFactory
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.repositories.company_repository import CompanyRepository
from app.services.company_service import CompanyService


class StubCollector(BaseCollector):
    def __init__(self, company_service: CompanyService, raw_items: list[dict[str, Any]]) -> None:
        super().__init__(company_service)
        self._raw_items = raw_items

    @property
    def name(self) -> str:
        return "stub"

    async def collect(self) -> list[Any]:
        return self._raw_items

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        return [
            CompanyLead(
                name=str(item["name"]),
                website=str(item["website"]),
                description=item.get("description"),
                source=str(item.get("source", "stub")),
                tags=item.get("tags", []),
            )
            for item in raw_items
        ]


@CollectorRegistry.register("test-stub")
class RegisteredStubCollector(StubCollector):
    pass


def test_collector_registry_register_get_list() -> None:
    assert "producthunt" in CollectorRegistry.list()
    assert "test-stub" in CollectorRegistry.list()
    assert CollectorRegistry.get("producthunt").__name__ == "ProductHuntCollector"


def test_collector_registry_unknown_collector() -> None:
    with pytest.raises(KeyError):
        CollectorRegistry.get("unknown-source")


def test_collector_factory_create_producthunt() -> None:
    service = CompanyService(CompanyRepository())
    collector = CollectorFactory.create("producthunt", service)

    assert collector.name == "producthunt"


@pytest.mark.asyncio
async def test_base_collector_run_pipeline(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = StubCollector(
        service,
        raw_items=[
            {"name": "Acme", "website": "https://acme.example", "source": "stub"},
            {"name": "Beta", "website": "https://beta.example", "source": "stub"},
        ],
    )

    result = await collector.run()

    assert result.collector_name == "stub"
    assert result.collected_count == 2
    assert result.normalized_count == 2
    assert result.valid_count == 2
    assert result.saved_count == 2
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_base_collector_validation_deduplicates_websites(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = StubCollector(
        service,
        raw_items=[
            {"name": "First", "website": "https://dup.example"},
            {"name": "Second", "website": "http://www.dup.example/"},
            {"name": "Valid", "website": "https://unique.example"},
        ],
    )

    result = await collector.run()

    assert result.collected_count == 3
    assert result.valid_count == 2
    assert result.saved_count == 2


@pytest.mark.asyncio
async def test_base_collector_validation_requires_name_and_website(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = StubCollector(
        service,
        raw_items=[
            {"name": "", "website": "https://missing-name.example"},
            {"name": "Missing Website", "website": ""},
            {"name": "Valid", "website": "https://valid.example"},
        ],
    )

    result = await collector.run()

    assert result.collected_count == 3
    assert result.valid_count == 1
    assert result.saved_count == 1


@pytest.mark.asyncio
async def test_base_collector_validate_normalizes_urls(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = StubCollector(service, raw_items=[])

    leads = [
        CompanyLead(name="Acme", website="https://www.acme.com/", source="stub"),
        CompanyLead(name="Beta", website="http://beta.com", source="stub"),
    ]

    validated = await collector.validate(leads)

    assert len(validated) == 2
    assert validated[0].website == "acme.com"
    assert validated[1].website == "beta.com"


@pytest.mark.asyncio
async def test_producthunt_collector_returns_empty(test_db: Any) -> None:
    service = CompanyService(CompanyRepository())
    collector = CollectorFactory.create("producthunt", service)

    with patch(
        "app.collectors.producthunt.fetch_latest_product_hunt_posts",
        new=AsyncMock(return_value=([], 0)),
    ):
        result = await collector.run()

    assert result.collector_name == "producthunt"
    assert result.collected_count == 0
    assert result.normalized_count == 0
    assert result.valid_count == 0
    assert result.saved_count == 0
