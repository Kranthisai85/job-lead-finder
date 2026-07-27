from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Generic, Sequence, TypeVar

from beanie import Document
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.exceptions import DuplicateRecordError, RepositoryError

ModelType = TypeVar("ModelType", bound=Document)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType]) -> None:
        self.model = model
        self.repository_name = self.__class__.__name__
        self.collection_name = getattr(self.model.Settings, "name", self.model.__name__.lower())
        self.logger = logging.getLogger(__name__)

    def _normalize_id(self, record_id: str | ObjectId) -> ObjectId:
        if isinstance(record_id, ObjectId):
            return record_id
        return ObjectId(record_id)

    def _log_success(self, operation: str, started_at: float) -> None:
        duration_ms = (perf_counter() - started_at) * 1000
        self.logger.info(
            "repository=%s collection=%s operation=%s duration_ms=%.2f success=true",
            self.repository_name,
            self.collection_name,
            operation,
            duration_ms,
        )

    def _log_failure(self, operation: str, started_at: float, error: Exception) -> None:
        duration_ms = (perf_counter() - started_at) * 1000
        self.logger.error(
            "repository=%s collection=%s operation=%s duration_ms=%.2f success=false error=%s",
            self.repository_name,
            self.collection_name,
            operation,
            duration_ms,
            error.__class__.__name__,
            exc_info=True,
        )

    def _map_exception(self, error: Exception) -> RepositoryError:
        if isinstance(error, DuplicateKeyError):
            return DuplicateRecordError("Duplicate record detected")
        return RepositoryError("Repository operation failed")

    async def create(self, payload: dict[str, Any] | ModelType) -> ModelType:
        operation = "create"
        started_at = perf_counter()
        try:
            document = payload if isinstance(payload, self.model) else self.model(**payload)
            created = await document.insert()
            self._log_success(operation, started_at)
            return created
        except (PyMongoError, DuplicateKeyError, ValueError) as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def update(
        self, record_id: str | ObjectId, update_data: dict[str, Any]
    ) -> ModelType | None:
        operation = "update"
        started_at = perf_counter()
        try:
            normalized_id = self._normalize_id(record_id)
            existing = await self.model.get(normalized_id)
            if existing is None:
                self._log_success(operation, started_at)
                return None
            for field_name, field_value in update_data.items():
                setattr(existing, field_name, field_value)
            updated = await existing.save()
            self._log_success(operation, started_at)
            return updated
        except (PyMongoError, DuplicateKeyError, ValueError) as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def delete(self, record_id: str | ObjectId) -> bool:
        operation = "delete"
        started_at = perf_counter()
        try:
            normalized_id = self._normalize_id(record_id)
            document = await self.model.get(normalized_id)
            if document is None:
                self._log_success(operation, started_at)
                return False
            await document.delete()
            self._log_success(operation, started_at)
            return True
        except (PyMongoError, ValueError) as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def find_by_id(self, record_id: str | ObjectId) -> ModelType | None:
        operation = "find_by_id"
        started_at = perf_counter()
        try:
            normalized_id = self._normalize_id(record_id)
            result = await self.model.get(normalized_id)
            self._log_success(operation, started_at)
            return result
        except (PyMongoError, ValueError) as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def find_one(self, filters: dict[str, Any]) -> ModelType | None:
        operation = "find_one"
        started_at = perf_counter()
        try:
            result = await self.model.find_one(filters)
            self._log_success(operation, started_at)
            return result
        except PyMongoError as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def find_many(
        self,
        filters: dict[str, Any],
        skip: int = 0,
        limit: int | None = None,
        sort: Sequence[tuple[str, Any]] | None = None,
    ) -> list[ModelType]:
        operation = "find_many"
        started_at = perf_counter()
        try:
            query = self.model.find(filters)
            if sort:
                query = query.sort(list(sort))
            if skip:
                query = query.skip(skip)
            if limit is not None:
                query = query.limit(limit)
            results = await query.to_list()
            self._log_success(operation, started_at)
            return results
        except PyMongoError as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        sort: Sequence[tuple[str, Any]] | None = None,
    ) -> list[ModelType]:
        operation = "list"
        started_at = perf_counter()
        try:
            query = self.model.find_all()
            if sort:
                query = query.sort(list(sort))
            results = await query.skip(skip).limit(limit).to_list()
            self._log_success(operation, started_at)
            return results
        except PyMongoError as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def exists(self, filters: dict[str, Any]) -> bool:
        operation = "exists"
        started_at = perf_counter()
        try:
            count = await self.model.find(filters).limit(1).count()
            self._log_success(operation, started_at)
            return count > 0
        except PyMongoError as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        operation = "count"
        started_at = perf_counter()
        try:
            query_filters = filters or {}
            total = await self.model.find(query_filters).count()
            self._log_success(operation, started_at)
            return total
        except PyMongoError as error:
            self._log_failure(operation, started_at, error)
            raise self._map_exception(error) from error

    async def paginate(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: Sequence[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        operation = "paginate"
        started_at = perf_counter()
        try:
            if page < 1:
                raise ValueError("page must be >= 1")
            if page_size < 1:
                raise ValueError("page_size must be >= 1")

            query_filters = filters or {}
            skip = (page - 1) * page_size
            total = await self.model.find(query_filters).count()
            items = await self.find_many(query_filters, skip=skip, limit=page_size, sort=sort)
            self._log_success(operation, started_at)
            return {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            }
        except (PyMongoError, ValueError, RepositoryError) as error:
            self._log_failure(operation, started_at, error)
            if isinstance(error, RepositoryError):
                raise
            raise self._map_exception(error) from error
