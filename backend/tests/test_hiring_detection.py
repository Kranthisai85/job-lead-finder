from __future__ import annotations

import pytest

from app.crawler.types import WebsiteProfile
from app.hiring_detection.ats import detect_ats_provider
from app.hiring_detection.service import HiringDetectionService


def make_profile(
    html: str = "",
    *,
    url: str = "https://acme.example",
    career_pages: list[str] | None = None,
    jobs_pages: list[str] | None = None,
) -> WebsiteProfile:
    return WebsiteProfile(
        url=url,
        final_url=f"{url.rstrip('/')}/",
        title="Acme",
        career_pages=career_pages or [],
        metadata={
            "html": html,
            "jobs_pages": jobs_pages or [],
            "internal_links": [],
            "external_links": [],
        },
        valid=True,
    )


def detect(profile: WebsiteProfile) -> object:
    return HiringDetectionService(fetch_extra_pages=False).detect(profile)


GREENHOUSE_HTML = """
<html>
  <body>
    <h1>Open Roles</h1>
    <a href="https://boards.greenhouse.io/acme/jobs/123">Senior Flutter Engineer</a>
    <a href="https://boards.greenhouse.io/acme/jobs/456">Frontend Developer — Remote</a>
  </body>
</html>
"""

LEVER_HTML = """
<html>
  <body>
    <div class="posting">
      <a href="https://jobs.lever.co/acme/flutter-dev">Flutter Developer</a>
      <span>Remote · Full-time</span>
    </div>
  </body>
</html>
"""

WORKABLE_HTML = """
<html>
  <body>
    <a href="https://apply.workable.com/acme/j/ABC123/">Mobile Engineer (React Native)</a>
    <p>Hybrid · Engineering</p>
  </body>
</html>
"""

SIMPLE_CAREERS_HTML = """
<html>
  <body>
    <h1>Careers</h1>
    <ul>
      <li><a href="/careers/software-engineer">Software Engineer — San Francisco</a></li>
      <li><a href="/careers/backend">Backend Engineer</a></li>
    </ul>
  </body>
</html>
"""

FLUTTER_HTML = """
<html>
  <body>
    <h1>We're hiring</h1>
    <a href="/jobs/flutter">Senior Flutter Developer</a>
    <p>Remote full-time Flutter Engineer role</p>
  </body>
</html>
"""

MOBILE_HTML = """
<html>
  <body>
    <a href="/jobs/mobile">Mobile Developer — iOS & Android</a>
  </body>
</html>
"""

REACT_NATIVE_HTML = """
<html>
  <body>
    <a href="/careers/rn">React Native Engineer</a>
  </body>
</html>
"""

FRONTEND_HTML = """
<html>
  <body>
    <a href="/jobs/frontend">Frontend Engineer (React)</a>
  </body>
</html>
"""

NO_CAREERS_HTML = """
<html>
  <body>
    <h1>Welcome to Acme</h1>
    <p>We build analytics tools for startups.</p>
  </body>
</html>
"""

DUPLICATE_HTML = """
<html>
  <body>
    <a href="/jobs/flutter-dev">Flutter Developer</a>
    <div><a href="/jobs/flutter-dev">Flutter Developer</a></div>
  </body>
</html>
"""


def test_detect_ats_providers() -> None:
    assert detect_ats_provider("https://boards.greenhouse.io/acme") == "Greenhouse"
    assert detect_ats_provider("https://jobs.lever.co/acme") == "Lever"
    assert detect_ats_provider("https://apply.workable.com/acme") == "Workable"
    assert detect_ats_provider("https://jobs.ashbyhq.com/acme") == "Ashby"
    assert detect_ats_provider("https://acme.myworkdayjobs.com") == "Workday"


def test_greenhouse_page() -> None:
    report = detect(make_profile(GREENHOUSE_HTML, url="https://boards.greenhouse.io/acme"))
    assert report.jobs_found >= 2
    assert report.provider == "Greenhouse"
    assert report.flutter_jobs >= 1
    assert report.frontend_jobs >= 1
    assert report.confidence > 0
    assert any("Flutter" in job.title for job in report.opportunities)


def test_lever_page() -> None:
    report = detect(make_profile(LEVER_HTML, url="https://jobs.lever.co/acme"))
    assert report.jobs_found >= 1
    assert report.provider == "Lever"
    assert report.flutter_jobs >= 1
    best = report.best_job
    assert best is not None
    assert "Flutter" in best.title


def test_workable_page() -> None:
    report = detect(make_profile(WORKABLE_HTML, url="https://apply.workable.com/acme"))
    assert report.jobs_found >= 1
    assert report.provider == "Workable"
    assert report.mobile_jobs >= 1
    assert any("react native" in " ".join(job.matched_keywords) for job in report.opportunities)


def test_simple_html_careers_page() -> None:
    report = detect(
        make_profile(
            SIMPLE_CAREERS_HTML,
            career_pages=["https://acme.example/careers"],
        )
    )
    assert report.jobs_found >= 1
    assert report.engineering_jobs >= 1
    assert report.has_engineering_careers_page is True


def test_flutter_hiring() -> None:
    report = detect(make_profile(FLUTTER_HTML))
    assert report.flutter_jobs >= 1
    assert report.mobile_jobs >= 1
    assert report.jobs_found >= 1
    assert any("flutter" in kw for job in report.opportunities for kw in job.matched_keywords)


def test_mobile_hiring() -> None:
    report = detect(make_profile(MOBILE_HTML))
    assert report.mobile_jobs >= 1
    assert report.jobs_found >= 1


def test_react_native_hiring() -> None:
    report = detect(make_profile(REACT_NATIVE_HTML))
    assert report.mobile_jobs >= 1
    assert report.frontend_jobs >= 1
    assert any(
        "react native" in " ".join(job.matched_keywords).lower() for job in report.opportunities
    )


def test_frontend_hiring() -> None:
    report = detect(make_profile(FRONTEND_HTML))
    assert report.frontend_jobs >= 1
    assert report.engineering_jobs >= 1


def test_no_careers_page() -> None:
    report = detect(make_profile(NO_CAREERS_HTML))
    assert report.jobs_found == 0
    assert report.flutter_jobs == 0
    assert report.provider is None
    assert report.opportunities == []


def test_duplicate_jobs_deduped() -> None:
    report = detect(make_profile(DUPLICATE_HTML))
    assert report.jobs_found == 1
    assert report.flutter_jobs == 1


def test_remote_engineering_flag() -> None:
    html = """
    <html><body>
      <a href="/jobs/se">Software Engineer — Remote</a>
    </body></html>
    """
    report = detect(make_profile(html))
    assert report.engineering_jobs >= 1
    assert report.has_remote_engineering is True
    assert any(job.remote is True for job in report.opportunities)


def test_hiring_logging_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        detect(make_profile(FLUTTER_HTML))
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "jobs_found=" in messages
    assert "flutter_jobs=" in messages
    assert "provider=" in messages
    assert "best_job=" in messages
    assert "confidence=" in messages
