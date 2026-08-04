from app.crawler.types import WebsiteProfile
from app.technology.detector import build_default_engine
from app.technology.rules import (
    CloudflareRule,
    DetectionContext,
    NextJSRule,
    ReactRule,
    StripeRule,
    TailwindRule,
)
from app.technology.service import TechnologyDetectionService


def make_profile(html: str = "", headers: dict[str, str] | None = None) -> WebsiteProfile:
    return WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme",
        metadata={
            "html": html,
            "headers": headers or {},
        },
    )


def test_react_detection() -> None:
    match = ReactRule().evaluate(
        DetectionContext(html='<script src="/static/react-dom.js"></script>')
    )
    assert match.matched is True
    assert match.confidence >= 75


def test_nextjs_detection() -> None:
    match = NextJSRule().evaluate(
        DetectionContext(html='<script id="__NEXT_DATA__" type="application/json">{}</script>')
    )
    assert match.matched is True
    assert match.confidence >= 90


def test_tailwind_detection() -> None:
    match = TailwindRule().evaluate(
        DetectionContext(html='<script src="https://cdn.tailwindcss.com"></script>')
    )
    assert match.matched is True


def test_cloudflare_detection() -> None:
    match = CloudflareRule().evaluate(
        DetectionContext(html="", headers={"server": "cloudflare", "cf-ray": "abc123"})
    )
    assert match.matched is True
    assert any("cf-ray" in item for item in match.evidence)


def test_stripe_detection() -> None:
    match = StripeRule().evaluate(
        DetectionContext(html='<script src="https://js.stripe.com/v3/"></script>')
    )
    assert match.matched is True


def test_multiple_technologies() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">{}</script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://js.stripe.com/v3/"></script>
    """
    service = TechnologyDetectionService()
    report = service.detect(make_profile(html=html, headers={"server": "cloudflare"}))

    names = {tech.name for tech in report.technologies}
    assert "Next.js" in names
    assert "Tailwind" in names
    assert "Stripe" in names
    assert "Cloudflare" in names
    assert report.detected_count >= 4


def test_no_technologies() -> None:
    service = TechnologyDetectionService()
    report = service.detect(make_profile(html="<html><body>Hello world</body></html>"))

    assert report.detected_count == 0
    assert report.technologies == []


def test_confidence_ordering() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">{}</script>
    <div data-reactroot></div>
    <script src="https://cdn.tailwindcss.com"></script>
    """
    service = TechnologyDetectionService()
    report = service.detect(make_profile(html=html))

    confidences = [tech.confidence for tech in report.technologies]
    assert confidences == sorted(confidences, reverse=True)


def test_minimum_confidence_filter() -> None:
    engine = build_default_engine(minimum_confidence=95)
    service = TechnologyDetectionService(engine=engine)
    report = service.detect(
        make_profile(html='<script src="https://cdn.tailwindcss.com"></script>')
    )

    assert all(tech.confidence >= 95 for tech in report.technologies)
    assert "Tailwind" not in {tech.name for tech in report.technologies}


def test_enabled_technologies_filter() -> None:
    engine = build_default_engine(enabled_technologies={"stripe"})
    service = TechnologyDetectionService(engine=engine)
    report = service.detect(
        make_profile(
            html="""
            <script id="__NEXT_DATA__" type="application/json">{}</script>
            <script src="https://js.stripe.com/v3/"></script>
            """
        )
    )

    assert report.detected_count == 1
    assert report.technologies[0].name == "Stripe"
