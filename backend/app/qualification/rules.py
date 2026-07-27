from abc import ABC, abstractmethod
from typing import ClassVar

from app.collectors.types import CompanyLead
from app.qualification.types import RuleEvaluation


class BaseRule(ABC):
    name: ClassVar[str]

    @abstractmethod
    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        raise NotImplementedError


class WebsiteExistsRule(BaseRule):
    name = "website_exists"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.website and lead.website.strip():
            return RuleEvaluation(points=20, reasons=["Website exists"])
        return RuleEvaluation(warnings=["Website is missing"], blocking=True)


class CompanyNameExistsRule(BaseRule):
    name = "company_name_exists"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.name and lead.name.strip():
            return RuleEvaluation(points=10, reasons=["Company name exists"])
        return RuleEvaluation(warnings=["Company name is missing"], blocking=True)


class DescriptionExistsRule(BaseRule):
    name = "description_exists"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.description and lead.description.strip():
            return RuleEvaluation(points=10, reasons=["Description exists"])
        return RuleEvaluation(warnings=["Description is missing"])


class NotLocalhostRule(BaseRule):
    name = "not_localhost"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        website = lead.website.lower()
        if "localhost" in website or website.startswith("127.0.0.1"):
            return RuleEvaluation(warnings=["Website is localhost"], blocking=True)
        return RuleEvaluation(reasons=["Website is not localhost"])


class NotGithubIoRule(BaseRule):
    name = "not_github_io"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.website.lower().endswith("github.io"):
            return RuleEvaluation(warnings=["Website uses github.io"], blocking=True)
        return RuleEvaluation(reasons=["Website is not github.io"])


class NotVercelAppRule(BaseRule):
    name = "not_vercel_app"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.website.lower().endswith("vercel.app"):
            return RuleEvaluation(warnings=["Website uses vercel.app"], blocking=True)
        return RuleEvaluation(reasons=["Website is not vercel.app"])


class NotNetlifyAppRule(BaseRule):
    name = "not_netlify_app"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.website.lower().endswith("netlify.app"):
            return RuleEvaluation(warnings=["Website uses netlify.app"], blocking=True)
        return RuleEvaluation(reasons=["Website is not netlify.app"])


class NotNotionSiteRule(BaseRule):
    name = "not_notion_site"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.website.lower().endswith("notion.site"):
            return RuleEvaluation(warnings=["Website uses notion.site"], blocking=True)
        return RuleEvaluation(reasons=["Website is not notion.site"])


class DescriptionLengthRule(BaseRule):
    name = "description_length"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.description and len(lead.description.strip()) > 40:
            return RuleEvaluation(points=15, reasons=["Description length exceeds 40 characters"])
        return RuleEvaluation(warnings=["Description is too short for bonus points"])


class HasTopicRule(BaseRule):
    name = "has_topic"

    def evaluate(self, lead: CompanyLead) -> RuleEvaluation:
        if lead.tags:
            return RuleEvaluation(points=10, reasons=["Has at least one topic/tag"])
        return RuleEvaluation(warnings=["No topics/tags provided"])


DEFAULT_RULES: list[type[BaseRule]] = [
    WebsiteExistsRule,
    CompanyNameExistsRule,
    DescriptionExistsRule,
    NotLocalhostRule,
    NotGithubIoRule,
    NotVercelAppRule,
    NotNetlifyAppRule,
    NotNotionSiteRule,
    DescriptionLengthRule,
    HasTopicRule,
]

ALL_RULE_NAMES = [rule.name for rule in DEFAULT_RULES]
