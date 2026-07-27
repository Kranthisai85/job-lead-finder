from collections.abc import Callable

from app.collectors.base import BaseCollector


class CollectorRegistry:
    _collectors: dict[str, type[BaseCollector]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[BaseCollector]], type[BaseCollector]]:
        def decorator(collector_cls: type[BaseCollector]) -> type[BaseCollector]:
            cls._collectors[name.lower()] = collector_cls
            return collector_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseCollector]:
        collector_cls = cls._collectors.get(name.lower())
        if collector_cls is None:
            raise KeyError(f"Collector '{name}' is not registered")
        return collector_cls

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._collectors.keys())
