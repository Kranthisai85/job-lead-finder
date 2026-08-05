"""Company Intelligence v2 DTOs and persistence document."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pymongo import IndexModel

from app.models.base import BaseDocument

BusinessModel = Literal[
    "SaaS",
    "Marketplace",
    "Agency",
    "Developer Tool",
    "Ecommerce",
    "Open Source",
    "AI Platform",
    "Enterprise Software",
    "Consumer App",
    "FinTech",
    "Healthcare",
    "EdTech",
]

TargetCustomer = Literal[
    "B2B",
    "B2C",
    "Enterprise",
    "SMB",
    "Startup",
    "Developers",
    "Creators",
    "Students",
]

PricingModel = Literal[
    "Free",
    "Freemium",
    "Paid",
    "Subscription",
    "Enterprise",
    "Unknown",
]

CompanyStage = Literal[
    "Idea",
    "MVP",
    "Early Startup",
    "Growth",
    "Scale-up",
    "Enterprise",
]

BUSINESS_MODELS: tuple[str, ...] = (
    "SaaS",
    "Marketplace",
    "Agency",
    "Developer Tool",
    "Ecommerce",
    "Open Source",
    "AI Platform",
    "Enterprise Software",
    "Consumer App",
    "FinTech",
    "Healthcare",
    "EdTech",
)

TARGET_CUSTOMERS: tuple[str, ...] = (
    "B2B",
    "B2C",
    "Enterprise",
    "SMB",
    "Startup",
    "Developers",
    "Creators",
    "Students",
)

PRICING_MODELS: tuple[str, ...] = (
    "Free",
    "Freemium",
    "Paid",
    "Subscription",
    "Enterprise",
    "Unknown",
)

COMPANY_STAGES: tuple[str, ...] = (
    "Idea",
    "MVP",
    "Early Startup",
    "Growth",
    "Scale-up",
    "Enterprise",
)


class CompanyIntelligenceReport(BaseModel):
    """Structured company intelligence extracted from website + hiring signals."""

    url: str = ""
    industry: str | None = None
    subcategory: str | None = None
    business_model: str | None = None
    target_customer: str | None = None
    pricing_model: str | None = None
    company_stage: str | None = None
    estimated_team_size: str | None = None
    estimated_maturity: str | None = None
    competitors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    funding_status: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Extraction helpers / qualification signals
    main_product: str | None = None
    product_category: str | None = None
    has_pricing_page: bool = False
    is_b2b_saas: bool = False
    is_enterprise_software: bool = False
    is_developer_tools: bool = False
    is_consumer_only: bool = False
    has_clear_icp: bool = False
    pages_scanned: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


class CompanyIntelligenceDocument(BaseDocument):
    """Persisted company intelligence — separate from Company model."""

    company_id: str
    url: str | None = None
    industry: str | None = None
    subcategory: str | None = None
    business_model: str | None = None
    target_customer: str | None = None
    pricing_model: str | None = None
    company_stage: str | None = None
    estimated_team_size: str | None = None
    estimated_maturity: str | None = None
    competitors: list[str] = []
    keywords: list[str] = []
    pain_points: list[str] = []
    opportunities: list[str] = []
    funding_status: str | None = None
    confidence: float | None = None
    main_product: str | None = None
    product_category: str | None = None
    has_pricing_page: bool = False
    is_b2b_saas: bool = False
    is_enterprise_software: bool = False
    is_developer_tools: bool = False
    is_consumer_only: bool = False
    has_clear_icp: bool = False
    signals: list[str] = []

    class Settings:
        name = "company_intelligence"
        indexes = [
            IndexModel([("company_id", 1)], unique=True),
            IndexModel([("business_model", 1)]),
            IndexModel([("industry", 1)]),
            IndexModel([("created_at", -1)]),
        ]
