"""Configurable keywords, ATS hosts, and hiring page paths."""

from __future__ import annotations

from dataclasses import dataclass, field


HIRING_PAGE_PATHS: tuple[str, ...] = (
    "/careers",
    "/jobs",
    "/join-us",
    "/work-with-us",
    "/hiring",
    "/openings",
    "/team",
    "/company/careers",
)

MAX_HIRING_PAGES = 6
HIRING_PAGE_TIMEOUT_S = 8.0

ATS_PROVIDERS: dict[str, tuple[str, ...]] = {
    "Greenhouse": ("greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io"),
    "Lever": ("lever.co", "jobs.lever.co"),
    "Ashby": ("ashbyhq.com", "jobs.ashbyhq.com"),
    "Workable": ("workable.com", "apply.workable.com"),
    "Teamtailor": ("teamtailor.com",),
    "BreezyHR": ("breezy.hr", "breezyhr.com"),
    "Recruitee": ("recruitee.com",),
    "SmartRecruiters": ("smartrecruiters.com",),
    "Workday": ("myworkdayjobs.com", "workday.com"),
    "Notion Jobs": ("notion.site", "notion.so"),
}

HIRING_KEYWORDS: tuple[str, ...] = (
    "flutter developer",
    "flutter engineer",
    "flutter",
    "react native",
    "mobile developer",
    "mobile engineer",
    "android",
    "ios",
    "react developer",
    "frontend engineer",
    "frontend developer",
    "front-end engineer",
    "front-end developer",
    "full stack engineer",
    "full-stack engineer",
    "fullstack engineer",
    "software engineer",
    "software developer",
    "backend engineer",
    "back-end engineer",
)

FLUTTER_KEYWORDS: frozenset[str] = frozenset({"flutter", "flutter developer", "flutter engineer"})
MOBILE_KEYWORDS: frozenset[str] = frozenset(
    {
        "flutter",
        "flutter developer",
        "flutter engineer",
        "react native",
        "mobile developer",
        "mobile engineer",
        "android",
        "ios",
    }
)
FRONTEND_KEYWORDS: frozenset[str] = frozenset(
    {
        "react developer",
        "react native",
        "frontend engineer",
        "frontend developer",
        "front-end engineer",
        "front-end developer",
    }
)
ENGINEERING_KEYWORDS: frozenset[str] = frozenset(
    {
        *FLUTTER_KEYWORDS,
        *MOBILE_KEYWORDS,
        *FRONTEND_KEYWORDS,
        "full stack engineer",
        "full-stack engineer",
        "fullstack engineer",
        "software engineer",
        "software developer",
        "backend engineer",
        "back-end engineer",
    }
)

SENIORITY_KEYWORDS: tuple[str, ...] = (
    "intern",
    "junior",
    "mid-level",
    "mid level",
    "mid",
    "senior",
    "lead",
    "principal",
    "staff",
)

REMOTE_KEYWORDS: tuple[str, ...] = ("remote", "work from home", "wfh", "distributed")
HYBRID_KEYWORDS: tuple[str, ...] = ("hybrid",)
ONSITE_KEYWORDS: tuple[str, ...] = ("on-site", "onsite", "in-office", "office-based")

EMPLOYMENT_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "full_time": ("full-time", "full time", "permanent"),
    "part_time": ("part-time", "part time"),
    "contract": ("contract", "contractor", "freelance"),
    "internship": ("internship", "intern"),
}


@dataclass(frozen=True, slots=True)
class HiringDetectionConfig:
    page_paths: tuple[str, ...] = HIRING_PAGE_PATHS
    max_pages: int = MAX_HIRING_PAGES
    timeout_s: float = HIRING_PAGE_TIMEOUT_S
    ats_providers: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(ATS_PROVIDERS))
    hiring_keywords: tuple[str, ...] = HIRING_KEYWORDS


DEFAULT_HIRING_CONFIG = HiringDetectionConfig()
