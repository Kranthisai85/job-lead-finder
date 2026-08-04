from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BusinessCategory = Literal[
    "Developer Tools",
    "Healthcare",
    "Fintech",
    "EdTech",
    "HR",
    "Marketing",
    "CRM",
    "Cybersecurity",
    "AI",
    "Analytics",
    "Productivity",
    "Legal",
    "E-commerce",
    "Payments",
    "DevOps",
    "Infrastructure",
    "Open Source",
    "Communication",
]

PricingModel = Literal[
    "Free",
    "Freemium",
    "Paid",
    "Enterprise",
    "Custom Pricing",
]

TargetAudience = Literal[
    "Developers",
    "Designers",
    "Sales Teams",
    "HR Teams",
    "Students",
    "Teachers",
    "Startups",
    "Enterprises",
    "SMBs",
    "Agencies",
]

ProductType = Literal[
    "SaaS",
    "Marketplace",
    "API",
    "Mobile App",
    "Desktop App",
    "Browser Extension",
    "Platform",
    "Consulting",
]


class CompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str | None = None
    tagline: str | None = None
    short_description: str | None = None
    business_category: BusinessCategory | None = None
    industry: str | None = None
    product_type: ProductType | None = None
    target_audience: TargetAudience | None = None
    pricing_model: PricingModel | None = None
    primary_cta: str | None = None
    headquarters: str | None = None
    founded_year: int | None = None
    social_links: dict[str, list[str]] = Field(default_factory=dict)
    source_url: str | None = None
    confidence: float = 0.0
    signals: list[str] = Field(default_factory=list)
