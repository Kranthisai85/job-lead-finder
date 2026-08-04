from app.crawler.types import WebsiteProfile
from app.mobile_detection.detector import build_default_engine
from app.mobile_detection.rules import (
    AndroidIntentLinkRule,
    AppleAppStoreLinkRule,
    DetectionContext,
    DownloadAppButtonRule,
    GooglePlayLinkRule,
    SmartBannerRule,
    UniversalLinkRule,
)
from app.mobile_detection.service import MobileAppDetectionService


def make_profile(
    *,
    html: str = "",
    app_store_links: list[str] | None = None,
    play_store_links: list[str] | None = None,
    external_links: list[str] | None = None,
) -> WebsiteProfile:
    return WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme",
        app_store_links=app_store_links or [],
        play_store_links=play_store_links or [],
        metadata={
            "html": html,
            "external_links": external_links or [],
            "internal_links": [],
        },
    )


def test_google_play_link() -> None:
    match = GooglePlayLinkRule().evaluate(
        DetectionContext(
            links=["https://play.google.com/store/apps/details?id=com.acme"],
            play_store_links=["https://play.google.com/store/apps/details?id=com.acme"],
        )
    )
    assert match.matched is True
    assert match.android is True
    assert match.confidence >= 0.9


def test_app_store_link() -> None:
    match = AppleAppStoreLinkRule().evaluate(
        DetectionContext(
            links=["https://apps.apple.com/app/id123"],
            app_store_links=["https://apps.apple.com/app/id123"],
        )
    )
    assert match.matched is True
    assert match.ios is True


def test_both_stores() -> None:
    service = MobileAppDetectionService()
    result = service.detect(
        make_profile(
            app_store_links=["https://apps.apple.com/app/id123"],
            play_store_links=["https://play.google.com/store/apps/details?id=com.acme"],
        )
    )
    assert result.has_mobile_app is True
    assert result.android_detected is True
    assert result.ios_detected is True
    assert result.confidence >= 0.9


def test_no_app() -> None:
    service = MobileAppDetectionService()
    result = service.detect(make_profile(html="<html><body>Hello world</body></html>"))

    assert result.has_mobile_app is False
    assert result.confidence == 0.0
    assert result.android_detected is False
    assert result.ios_detected is False


def test_download_button() -> None:
    match = DownloadAppButtonRule().evaluate(
        DetectionContext(html="<a href='/app'>Get it on Google Play</a>")
    )
    assert match.matched is True
    assert match.android is True


def test_smart_banner() -> None:
    match = SmartBannerRule().evaluate(
        DetectionContext(html='<meta name="apple-itunes-app" content="app-id=123">')
    )
    assert match.matched is True
    assert match.ios is True


def test_universal_link() -> None:
    match = UniversalLinkRule().evaluate(
        DetectionContext(html='<link rel="alternate" href="ios-app://123/acme">')
    )
    assert match.matched is True


def test_android_intent_link() -> None:
    match = AndroidIntentLinkRule().evaluate(
        DetectionContext(links=["intent://scan/#Intent;scheme=zxing;end"])
    )
    assert match.matched is True
    assert match.android is True


def test_multiple_evidence() -> None:
    html = """
    <html>
      <head>
        <meta name="apple-itunes-app" content="app-id=123">
      </head>
      <body>
        <a href="https://play.google.com/store/apps/details?id=com.acme">Play</a>
        <a href="https://apps.apple.com/app/id123">App Store</a>
        <button>Open in App</button>
      </body>
    </html>
    """
    service = MobileAppDetectionService()
    result = service.detect(
        make_profile(
            html=html,
            external_links=[
                "https://play.google.com/store/apps/details?id=com.acme",
                "https://apps.apple.com/app/id123",
            ],
        )
    )

    assert result.has_mobile_app is True
    assert result.android_detected is True
    assert result.ios_detected is True
    assert len(result.evidence) >= 3
    assert result.evidence == sorted(result.evidence)


def test_confidence_ordering_via_max() -> None:
    service = MobileAppDetectionService()
    result = service.detect(
        make_profile(
            html="<a>Get the App</a>",
            play_store_links=["https://play.google.com/store/apps/details?id=com.acme"],
        )
    )
    assert result.confidence == 0.95


def test_minimum_confidence_filter() -> None:
    engine = build_default_engine(minimum_confidence=0.99)
    service = MobileAppDetectionService(engine=engine)
    result = service.detect(make_profile(html="<a>Get the App</a>"))

    assert result.has_mobile_app is False
