from __future__ import annotations

from collections.abc import Callable

from app.source_manager.base import BaseSourceCollector


class SourceRegistry:
    _collectors: dict[str, type[BaseSourceCollector]] = {}

    @classmethod
    def register(
        cls, name: str
    ) -> Callable[[type[BaseSourceCollector]], type[BaseSourceCollector]]:
        def decorator(
            collector_cls: type[BaseSourceCollector],
        ) -> type[BaseSourceCollector]:
            cls._collectors[name.lower()] = collector_cls
            return collector_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseSourceCollector]:
        collector_cls = cls._collectors.get(name.lower())
        if collector_cls is None:
            raise KeyError(f"Source collector '{name}' is not registered")
        return collector_cls

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._collectors.keys())

    @classmethod
    def create(cls, name: str) -> BaseSourceCollector:
        return cls.get(name)()
