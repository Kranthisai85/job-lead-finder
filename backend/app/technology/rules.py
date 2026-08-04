from abc import ABC, abstractmethod
from typing import ClassVar

from app.technology.types import RuleMatch


class DetectionContext:
    def __init__(
        self,
        *,
        html: str = "",
        headers: dict[str, str] | None = None,
        extra_text: str = "",
    ) -> None:
        self.html = html
        self.html_lower = html.lower()
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.extra_text = extra_text
        self.extra_lower = extra_text.lower()
        self.search_blob = f"{self.html_lower}\n{self.extra_lower}"


class BaseTechnologyRule(ABC):
    name: ClassVar[str]
    category: ClassVar[str]

    @abstractmethod
    def evaluate(self, context: DetectionContext) -> RuleMatch:
        raise NotImplementedError


class MarkerRule(BaseTechnologyRule):
    markers: ClassVar[tuple[str, ...]] = ()
    header_markers: ClassVar[tuple[tuple[str, str], ...]] = ()
    confidence: ClassVar[int] = 80

    def evaluate(self, context: DetectionContext) -> RuleMatch:
        evidence: list[str] = []

        for marker in self.markers:
            if marker.lower() in context.search_blob:
                evidence.append(f"Found marker: {marker}")

        for header_name, expected in self.header_markers:
            actual = context.headers.get(header_name.lower(), "")
            if not actual:
                continue
            if expected and expected.lower() not in actual.lower():
                continue
            evidence.append(f"Found header {header_name}: {actual}")

        if not evidence:
            return RuleMatch(matched=False)

        confidence = min(100, self.confidence + max(0, (len(evidence) - 1) * 5))
        return RuleMatch(matched=True, confidence=confidence, evidence=evidence)


class ReactRule(MarkerRule):
    name = "React"
    category = "frontend"
    markers = ("react", "react-dom", "data-reactroot", "_next/static", "__NEXT_DATA__")
    confidence = 75


class VueRule(MarkerRule):
    name = "Vue"
    category = "frontend"
    markers = ("vue.js", "vue.min.js", "data-v-", "__vue__", "nuxt")
    confidence = 80


class AngularRule(MarkerRule):
    name = "Angular"
    category = "frontend"
    markers = ("ng-version", "angular.js", "angular.min.js", "ng-app")
    confidence = 85


class NextJSRule(MarkerRule):
    name = "Next.js"
    category = "frontend"
    markers = ("_next/static", "__NEXT_DATA__", "next/dist", "next.js")
    confidence = 90


class NuxtRule(MarkerRule):
    name = "Nuxt"
    category = "frontend"
    markers = ("__NUXT__", "_nuxt/", "nuxt.js")
    confidence = 90


class SvelteRule(MarkerRule):
    name = "Svelte"
    category = "frontend"
    markers = ("svelte", "__svelte")
    confidence = 80


class BootstrapRule(MarkerRule):
    name = "Bootstrap"
    category = "frontend"
    markers = (
        "bootstrap.min.css",
        "bootstrap.min.js",
        "bootstrap.css",
        "cdn.jsdelivr.net/npm/bootstrap",
    )
    confidence = 85


class TailwindRule(MarkerRule):
    name = "Tailwind"
    category = "frontend"
    markers = ("tailwindcss", "tailwind.min.css", "cdn.tailwindcss.com")
    confidence = 85


class JQueryRule(MarkerRule):
    name = "jQuery"
    category = "frontend"
    markers = ("jquery.min.js", "jquery.js", "cdnjs.cloudflare.com/ajax/libs/jquery")
    confidence = 85


class LaravelRule(MarkerRule):
    name = "Laravel"
    category = "backend"
    markers = ("laravel", "csrf-token", "laravel_session")
    confidence = 70


class DjangoRule(MarkerRule):
    name = "Django"
    category = "backend"
    markers = ("csrfmiddlewaretoken", "django", "csrftoken")
    confidence = 75


class RubyOnRailsRule(MarkerRule):
    name = "Ruby on Rails"
    category = "backend"
    markers = ("rails-ujs", "data-turbolinks", "csrf-param", "ruby on rails")
    confidence = 75


class ExpressRule(MarkerRule):
    name = "Express"
    category = "backend"
    markers = ("express",)
    header_markers = (("x-powered-by", "express"),)
    confidence = 80


class AspNetRule(MarkerRule):
    name = "ASP.NET"
    category = "backend"
    markers = ("aspnet", "asp.net", "__viewstate", "webforms")
    header_markers = (("x-powered-by", "asp.net"), ("x-aspnet-version", ""))
    confidence = 80


class CloudflareRule(MarkerRule):
    name = "Cloudflare"
    category = "hosting"
    markers = ("cdnjs.cloudflare.com", "cloudflare")
    header_markers = (("server", "cloudflare"), ("cf-ray", ""), ("cf-cache-status", ""))
    confidence = 90


class VercelRule(MarkerRule):
    name = "Vercel"
    category = "hosting"
    markers = ("vercel", "vercel.app", "_vercel")
    header_markers = (("server", "vercel"), ("x-vercel-id", ""))
    confidence = 90


class NetlifyRule(MarkerRule):
    name = "Netlify"
    category = "hosting"
    markers = ("netlify", "netlify.app", "netlify-identity")
    header_markers = (("server", "netlify"), ("x-nf-request-id", ""))
    confidence = 90


class AWSRule(MarkerRule):
    name = "AWS"
    category = "hosting"
    markers = ("amazonaws.com", "cloudfront.net", "aws-amplify")
    header_markers = (("server", "amazons3"), ("x-amz-cf-id", ""), ("x-amz-request-id", ""))
    confidence = 85


class GoogleCloudRule(MarkerRule):
    name = "Google Cloud"
    category = "hosting"
    markers = ("googleapis.com", "gstatic.com", "appspot.com", "googleusercontent.com")
    confidence = 70


class AzureRule(MarkerRule):
    name = "Azure"
    category = "hosting"
    markers = ("azurewebsites.net", "azureedge.net", "windows.net", "azure.com")
    confidence = 80


class GoogleAnalyticsRule(MarkerRule):
    name = "Google Analytics"
    category = "analytics"
    markers = ("google-analytics.com", "gtag(", "ga(", "analytics.js", "googletagmanager.com/gtag")
    confidence = 90


class GoogleTagManagerRule(MarkerRule):
    name = "Google Tag Manager"
    category = "analytics"
    markers = ("googletagmanager.com/gtm.js", "gtm.start", "GTM-")
    confidence = 90


class PlausibleRule(MarkerRule):
    name = "Plausible"
    category = "analytics"
    markers = ("plausible.io", "plausible.min.js")
    confidence = 95


class MixpanelRule(MarkerRule):
    name = "Mixpanel"
    category = "analytics"
    markers = ("mixpanel", "cdn.mxpnl.com")
    confidence = 90


class SegmentRule(MarkerRule):
    name = "Segment"
    category = "analytics"
    markers = ("cdn.segment.com", "analytics.min.js", "segment.com")
    confidence = 85


class HotjarRule(MarkerRule):
    name = "Hotjar"
    category = "analytics"
    markers = ("static.hotjar.com", "hotjar", "hj(")
    confidence = 90


class IntercomRule(MarkerRule):
    name = "Intercom"
    category = "customer_support"
    markers = ("widget.intercom.io", "intercom", "intercomSettings")
    confidence = 90


class CrispRule(MarkerRule):
    name = "Crisp"
    category = "customer_support"
    markers = ("client.crisp.chat", "crisp.chat")
    confidence = 95


class ZendeskRule(MarkerRule):
    name = "Zendesk"
    category = "customer_support"
    markers = ("static.zdassets.com", "zendesk", "zopim")
    confidence = 90


class DriftRule(MarkerRule):
    name = "Drift"
    category = "customer_support"
    markers = ("js.driftt.com", "drift.com", "driftt")
    confidence = 90


class StripeRule(MarkerRule):
    name = "Stripe"
    category = "payment"
    markers = ("js.stripe.com", "stripe.com", "Stripe(")
    confidence = 90


class PaddleRule(MarkerRule):
    name = "Paddle"
    category = "payment"
    markers = ("cdn.paddle.com", "paddle.js", "paddle.com")
    confidence = 90


class LemonSqueezyRule(MarkerRule):
    name = "LemonSqueezy"
    category = "payment"
    markers = ("lemonsqueezy.com", "assets.lemonsqueezy.com")
    confidence = 95


class ClerkRule(MarkerRule):
    name = "Clerk"
    category = "authentication"
    markers = ("clerk.accounts.dev", "clerk.com", "@clerk")
    confidence = 90


class Auth0Rule(MarkerRule):
    name = "Auth0"
    category = "authentication"
    markers = ("cdn.auth0.com", "auth0.com", "auth0-js")
    confidence = 90


class FirebaseAuthRule(MarkerRule):
    name = "Firebase Auth"
    category = "authentication"
    markers = ("firebase", "firebaseapp.com", "identitytoolkit.googleapis.com")
    confidence = 80


class SupabaseAuthRule(MarkerRule):
    name = "Supabase Auth"
    category = "authentication"
    markers = ("supabase.co", "supabase.js", "@supabase")
    confidence = 90


DEFAULT_TECHNOLOGY_RULES: list[type[BaseTechnologyRule]] = [
    ReactRule,
    VueRule,
    AngularRule,
    NextJSRule,
    NuxtRule,
    SvelteRule,
    BootstrapRule,
    TailwindRule,
    JQueryRule,
    LaravelRule,
    DjangoRule,
    RubyOnRailsRule,
    ExpressRule,
    AspNetRule,
    CloudflareRule,
    VercelRule,
    NetlifyRule,
    AWSRule,
    GoogleCloudRule,
    AzureRule,
    GoogleAnalyticsRule,
    GoogleTagManagerRule,
    PlausibleRule,
    MixpanelRule,
    SegmentRule,
    HotjarRule,
    IntercomRule,
    CrispRule,
    ZendeskRule,
    DriftRule,
    StripeRule,
    PaddleRule,
    LemonSqueezyRule,
    ClerkRule,
    Auth0Rule,
    FirebaseAuthRule,
    SupabaseAuthRule,
]

ALL_TECHNOLOGY_NAMES = [rule.name for rule in DEFAULT_TECHNOLOGY_RULES]
