from typing import Any

from pydantic import BaseModel, Field


class LinkClassification(BaseModel):
    contact_pages: list[str] = Field(default_factory=list)
    about_pages: list[str] = Field(default_factory=list)
    career_pages: list[str] = Field(default_factory=list)
    jobs_pages: list[str] = Field(default_factory=list)
    pricing_pages: list[str] = Field(default_factory=list)
    blog_pages: list[str] = Field(default_factory=list)
    documentation_pages: list[str] = Field(default_factory=list)
    api_pages: list[str] = Field(default_factory=list)


class SocialLinks(BaseModel):
    linkedin: list[str] = Field(default_factory=list)
    twitter: list[str] = Field(default_factory=list)
    github: list[str] = Field(default_factory=list)
    facebook: list[str] = Field(default_factory=list)
    instagram: list[str] = Field(default_factory=list)
    youtube: list[str] = Field(default_factory=list)
    discord: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)


class DownloadResult(BaseModel):
    url: str
    final_url: str
    status_code: int
    html: str
    response_time_ms: float
    headers: dict[str, str] = Field(default_factory=dict)


class WebsiteProfile(BaseModel):
    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    favicon: str | None = None
    language: str | None = None
    status_code: int | None = None
    response_time_ms: float | None = None
    technologies: list[str] = Field(default_factory=list)
    social_links: SocialLinks = Field(default_factory=SocialLinks)
    contact_pages: list[str] = Field(default_factory=list)
    career_pages: list[str] = Field(default_factory=list)
    blog_pages: list[str] = Field(default_factory=list)
    pricing_pages: list[str] = Field(default_factory=list)
    documentation_pages: list[str] = Field(default_factory=list)
    app_store_links: list[str] = Field(default_factory=list)
    play_store_links: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
