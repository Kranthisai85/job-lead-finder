import re
from abc import ABC, abstractmethod
from typing import ClassVar
from urllib.parse import urlparse

from app.mobile_detection.types import RuleMatch


class DetectionContext:
    def __init__(
        self,
        *,
        html: str = "",
        links: list[str] | None = None,
        app_store_links: list[str] | None = None,
        play_store_links: list[str] | None = None,
        extra_text: str = "",
    ) -> None:
        self.html = html
        self.html_lower = html.lower()
        self.links = links or []
        self.app_store_links = app_store_links or []
        self.play_store_links = play_store_links or []
        self.extra_text = extra_text
        self.extra_lower = extra_text.lower()
        self.search_blob = f"{self.html_lower}\n{self.extra_lower}\n" + "\n".join(
            link.lower() for link in self.links
        )


class BaseMobileRule(ABC):
    name: ClassVar[str]

    @abstractmethod
    def evaluate(self, context: DetectionContext) -> RuleMatch:
        raise NotImplementedError


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _find_links(context: DetectionContext, domains: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    candidates = context.links + context.app_store_links + context.play_store_links
    for link in candidates:
        host = urlparse(link).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if any(
            host == domain or host.endswith(f".{domain}") or domain in link.lower()
            for domain in domains
        ):
            matches.append(link)
    return _unique(matches)


class GooglePlayLinkRule(BaseMobileRule):
    name = "google_play_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        links = _unique(context.play_store_links + _find_links(context, ("play.google.com",)))
        if not links and "play.google.com" in context.search_blob:
            links = ["play.google.com"]
        if not links:
            return RuleMatch(matched=False)
        return RuleMatch(
            matched=True,
            confidence=0.95,
            evidence=[f"Google Play link detected: {link}" for link in links],
            detected_links=links,
            android=True,
        )


class AppleAppStoreLinkRule(BaseMobileRule):
    name = "apple_app_store_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        links = _unique(
            context.app_store_links + _find_links(context, ("apps.apple.com", "itunes.apple.com"))
        )
        if not links:
            for domain in ("apps.apple.com", "itunes.apple.com"):
                if domain in context.search_blob:
                    links.append(domain)
        links = _unique(links)
        if not links:
            return RuleMatch(matched=False)
        return RuleMatch(
            matched=True,
            confidence=0.95,
            evidence=[f"Apple App Store link detected: {link}" for link in links],
            detected_links=links,
            ios=True,
        )


class SmartBannerRule(BaseMobileRule):
    name = "smart_banner"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        evidence: list[str] = []
        ios = False
        android = False

        if "apple-itunes-app" in context.html_lower:
            evidence.append("Found apple-itunes-app smart banner meta tag")
            ios = True

        if "google-play-app" in context.html_lower:
            evidence.append("Found google-play-app smart banner meta tag")
            android = True

        if not evidence:
            return RuleMatch(matched=False)

        return RuleMatch(
            matched=True,
            confidence=0.9,
            evidence=evidence,
            android=android,
            ios=ios,
        )


class UniversalLinkRule(BaseMobileRule):
    name = "universal_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        patterns = (
            'rel="alternate"',
            "apple-app-site-association",
            "app-site-association",
            "android:host",
        )
        evidence = [
            f"Found universal link marker: {pattern}"
            for pattern in patterns
            if pattern in context.search_blob
        ]
        if not evidence:
            return RuleMatch(matched=False)
        return RuleMatch(
            matched=True,
            confidence=0.7,
            evidence=evidence,
            ios=True,
            android="android:host" in context.search_blob,
        )


class AndroidIntentLinkRule(BaseMobileRule):
    name = "android_intent_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        links = [link for link in context.links if link.lower().startswith("intent:")]
        if not links and "intent://" in context.search_blob:
            links = ["intent://"]
        if not links:
            return RuleMatch(matched=False)
        return RuleMatch(
            matched=True,
            confidence=0.85,
            evidence=[f"Android intent link detected: {link}" for link in links],
            detected_links=links,
            android=True,
        )


class DeepLinkRule(BaseMobileRule):
    name = "deep_link"

    CUSTOM_SCHEME_PATTERN = re.compile(r"\b([a-z][a-z0-9+\-.]*):\/\/", re.IGNORECASE)
    BLOCKED_SCHEMES = {
        "http",
        "https",
        "mailto",
        "tel",
        "sms",
        "ftp",
        "file",
        "data",
        "javascript",
        "about",
        "blob",
    }

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        evidence: list[str] = []
        links: list[str] = []

        for link in context.links:
            parsed = urlparse(link)
            scheme = parsed.scheme.lower()
            if scheme and scheme not in self.BLOCKED_SCHEMES and scheme != "intent":
                links.append(link)
                evidence.append(f"Custom deep link scheme detected: {link}")

        for match in self.CUSTOM_SCHEME_PATTERN.finditer(context.html):
            scheme = match.group(1).lower()
            if scheme in self.BLOCKED_SCHEMES or scheme == "intent":
                continue
            value = match.group(0)
            if value not in links:
                links.append(value)
                evidence.append(f"Custom URI scheme detected: {scheme}://")

        if not evidence:
            return RuleMatch(matched=False)

        return RuleMatch(
            matched=True,
            confidence=0.65,
            evidence=_unique(evidence),
            detected_links=_unique(links),
            android=True,
            ios=True,
        )


class DownloadAppButtonRule(BaseMobileRule):
    name = "download_app_button"

    PHRASES = (
        "download app",
        "get the app",
        "download on the app store",
        "download on app store",
        "get it on google play",
        "get it on the google play",
        "open in app",
        "open app",
        "install the app",
        "available on the app store",
        "available on google play",
    )

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        evidence = [
            f"Found mobile CTA text: {phrase}"
            for phrase in self.PHRASES
            if phrase in context.search_blob
        ]
        if not evidence:
            return RuleMatch(matched=False)

        ios = any("app store" in item.lower() for item in evidence)
        android = any("google play" in item.lower() for item in evidence)
        return RuleMatch(
            matched=True,
            confidence=0.75,
            evidence=evidence,
            android=android or not ios,
            ios=ios or not android,
        )


class FooterAppLinkRule(BaseMobileRule):
    name = "footer_app_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        footer_match = re.search(
            r"<footer[\s\S]*?</footer>",
            context.html,
            flags=re.IGNORECASE,
        )
        if not footer_match:
            return RuleMatch(matched=False)

        footer_html = footer_match.group(0).lower()
        evidence: list[str] = []
        links: list[str] = []
        android = False
        ios = False

        if "play.google.com" in footer_html:
            evidence.append("Google Play link found in footer")
            android = True
            links.append("play.google.com")
        if "apps.apple.com" in footer_html or "itunes.apple.com" in footer_html:
            evidence.append("App Store link found in footer")
            ios = True
            links.append("apps.apple.com")

        if not evidence:
            return RuleMatch(matched=False)

        return RuleMatch(
            matched=True,
            confidence=0.8,
            evidence=evidence,
            detected_links=_unique(links),
            android=android,
            ios=ios,
        )


class NavigationAppLinkRule(BaseMobileRule):
    name = "navigation_app_link"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        nav_match = re.search(r"<nav[\s\S]*?</nav>", context.html, flags=re.IGNORECASE)
        if not nav_match:
            return RuleMatch(matched=False)

        nav_html = nav_match.group(0).lower()
        evidence: list[str] = []
        links: list[str] = []
        android = False
        ios = False

        if "play.google.com" in nav_html:
            evidence.append("Google Play link found in navigation")
            android = True
            links.append("play.google.com")
        if "apps.apple.com" in nav_html or "itunes.apple.com" in nav_html:
            evidence.append("App Store link found in navigation")
            ios = True
            links.append("apps.apple.com")

        if not evidence:
            return RuleMatch(matched=False)

        return RuleMatch(
            matched=True,
            confidence=0.8,
            evidence=evidence,
            detected_links=_unique(links),
            android=android,
            ios=ios,
        )


class MobileCtaButtonRule(BaseMobileRule):
    name = "mobile_cta_button"

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        button_patterns = (
            r"<a[^>]*>[^<]*(download|get the app|open in app|open app)[^<]*</a>",
            r"<button[^>]*>[^<]*(download|get the app|open in app|open app)[^<]*</button>",
        )
        evidence: list[str] = []
        for pattern in button_patterns:
            for match in re.finditer(pattern, context.html, flags=re.IGNORECASE):
                evidence.append(f"Found mobile CTA button: {match.group(0).strip()[:120]}")

        if not evidence:
            return RuleMatch(matched=False)

        return RuleMatch(
            matched=True,
            confidence=0.7,
            evidence=_unique(evidence),
            android=True,
            ios=True,
        )


DEFAULT_MOBILE_RULES: list[type[BaseMobileRule]] = [
    GooglePlayLinkRule,
    AppleAppStoreLinkRule,
    SmartBannerRule,
    UniversalLinkRule,
    AndroidIntentLinkRule,
    DeepLinkRule,
    DownloadAppButtonRule,
    FooterAppLinkRule,
    NavigationAppLinkRule,
    MobileCtaButtonRule,
]
