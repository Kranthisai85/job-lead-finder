from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.collectors.types import CompanyLead
from app.db import mongo as mongo_module
from app.lead_generation.orchestrator import LeadGenerationOrchestrator
from app.lead_generation.service import LeadGenerationService
from app.lead_generation.types import LeadGenerationReport, LeadGenerationStatistics
from app.personalization.service import CompanyPersonalizationService
from app.pipeline.persistence import PipelinePersistenceService
from app.repositories.company_repository import CompanyRepository
from app.source_manager.types import SourceCollectionReport
from tests.test_personalization import make_lead


@pytest.mark.asyncio
async def test_ensure_mongo_ready_initializes_once() -> None:
    mongo_module._initialized = False
    mongo_module.client = None

    connect = AsyncMock()
    with (
        patch.object(mongo_module, "is_beanie_initialized", side_effect=[False, True, True]),
        patch.object(mongo_module, "connect_to_mongo", new=connect),
    ):
        await mongo_module.ensure_mongo_ready()
        await mongo_module.ensure_mongo_ready()

    connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_to_mongo_skips_when_beanie_already_initialized() -> None:
    mongo_module._initialized = False
    init_beanie = AsyncMock()
    motor_client = MagicMock()
    with (
        patch.object(mongo_module, "is_beanie_initialized", return_value=True),
        patch.object(mongo_module, "AsyncIOMotorClient", return_value=motor_client),
        patch.object(mongo_module, "init_beanie", new=init_beanie),
    ):
        await mongo_module.connect_to_mongo()

    motor_client.assert_not_called()
    init_beanie.assert_not_awaited()
    assert mongo_module._initialized is True


@pytest.mark.asyncio
async def test_lead_generation_service_cli_run_initializes_db_and_persists(
    test_db: Any,
) -> None:
    """Simulate CLI usage: service ensures DB, then persistence writes companies."""
    collection_service = AsyncMock()
    collection_service.collect_all = AsyncMock(
        return_value=SourceCollectionReport(
            collectors_run=["test"],
            total_found=1,
            unique_companies=[
                CompanyLead(
                    name="Acme CLI",
                    website="https://acme-cli.example",
                    description="CLI collected startup",
                    source="test",
                )
            ],
        )
    )

    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(side_effect=lambda seed: make_lead(company_name=seed.name))

    orchestrator = LeadGenerationOrchestrator(
        collection_service=collection_service,
        persistence_service=PipelinePersistenceService(),
        pipeline_service=pipeline_service,
        personalization_service=CompanyPersonalizationService(),
        ai_email_service=AsyncMock(),
        email_queue_service=AsyncMock(),
    )
    service = LeadGenerationService(orchestrator=orchestrator)

    # test_db already initialized Beanie; ensure_mongo_ready must be idempotent.
    report = await service.run(
        limit=1,
        persist=True,
        generate_emails=False,
        enqueue_emails=False,
    )

    assert report.statistics.processed == 1
    assert report.statistics.persisted == 1
    assert report.results[0].persisted is True
    assert report.results[0].company_id is not None
    assert report.results[0].success is True
    assert await CompanyRepository().count() == 1


@pytest.mark.asyncio
async def test_lead_generation_service_calls_ensure_mongo_when_persist_enabled() -> None:
    orchestrator = AsyncMock(spec=LeadGenerationOrchestrator)
    orchestrator.run = AsyncMock(
        return_value=LeadGenerationReport(
            statistics=LeadGenerationStatistics(processed=0, queued=0, duration_ms=1.0),
            success=True,
        )
    )
    service = LeadGenerationService(orchestrator=orchestrator)

    with patch("app.lead_generation.service.ensure_mongo_ready", new=AsyncMock()) as ensure:
        await service.run(persist=True, generate_emails=False, enqueue_emails=False)

    ensure.assert_awaited_once()


@pytest.mark.asyncio
async def test_lead_generation_service_skips_ensure_mongo_when_persist_disabled() -> None:
    orchestrator = AsyncMock(spec=LeadGenerationOrchestrator)
    orchestrator.run = AsyncMock(
        return_value=LeadGenerationReport(
            statistics=LeadGenerationStatistics(processed=0, queued=0, duration_ms=1.0),
            success=True,
        )
    )
    service = LeadGenerationService(orchestrator=orchestrator)

    with patch("app.lead_generation.service.ensure_mongo_ready", new=AsyncMock()) as ensure:
        await service.run(persist=False, generate_emails=False, enqueue_emails=False)

    ensure.assert_not_awaited()
