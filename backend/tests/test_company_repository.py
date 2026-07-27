from typing import Any

import pytest

from app.exceptions import DuplicateRecordError
from app.repositories.company_repository import CompanyRepository


@pytest.mark.asyncio
async def test_company_repository_crud_and_exists(test_db: Any) -> None:
    repository = CompanyRepository()

    created = await repository.create(
        {
            "name": "Acme",
            "website": "https://acme.example",
            "source": "product_hunt",
        }
    )
    assert created.id is not None

    found = await repository.find_by_id(created.id)
    assert found is not None
    assert found.name == "Acme"

    updated = await repository.update(created.id, {"name": "Acme Labs"})
    assert updated is not None
    assert updated.name == "Acme Labs"

    exists = await repository.exists({"website": "https://acme.example"})
    assert exists is True

    total = await repository.count()
    assert total == 1

    deleted = await repository.delete(created.id)
    assert deleted is True

    missing = await repository.find_by_id(created.id)
    assert missing is None


@pytest.mark.asyncio
async def test_company_repository_duplicate_record_error(test_db: Any) -> None:
    repository = CompanyRepository()
    await repository.create({"name": "A", "website": "https://dup.example"})

    with pytest.raises(DuplicateRecordError):
        await repository.create({"name": "B", "website": "https://dup.example"})


@pytest.mark.asyncio
async def test_company_repository_pagination(test_db: Any) -> None:
    repository = CompanyRepository()
    for index in range(5):
        await repository.create(
            {
                "name": f"Company {index}",
                "website": f"https://company-{index}.example",
                "source": "test",
            }
        )

    page_one = await repository.paginate(
        filters={"source": "test"}, page=1, page_size=2, sort=[("name", 1)]
    )
    page_two = await repository.paginate(
        filters={"source": "test"}, page=2, page_size=2, sort=[("name", 1)]
    )

    assert page_one["total"] == 5
    assert page_one["total_pages"] == 3
    assert len(page_one["items"]) == 2
    assert len(page_two["items"]) == 2
