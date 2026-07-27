from app.collectors.base import BaseCollector
from app.collectors.registry import CollectorRegistry
from app.services.company_service import CompanyService


class CollectorFactory:
    @staticmethod
    def create(name: str, company_service: CompanyService) -> BaseCollector:
        collector_cls = CollectorRegistry.get(name)
        return collector_cls(company_service)
