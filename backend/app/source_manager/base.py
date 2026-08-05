from __future__ import annotations

from abc import ABC, abstractmethod

from app.collectors.types import CompanyLead


class BaseSourceCollector(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def collect_leads(self) -> list[CompanyLead]:
        raise NotImplementedError
