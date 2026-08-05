import pytest

from app.utils.url import (
    canonical_lead_website,
    is_producthunt_redirect,
    is_usable_company_website,
    normalize_website,
    website_identity,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://abc.com/", "abc.com"),
        ("https://abc.com", "abc.com"),
        ("http://abc.com", "abc.com"),
        ("  https://www.abc.com/path  ", "abc.com"),
    ],
)
def test_normalize_website(raw: str, expected: str) -> None:
    assert normalize_website(raw) == expected


def test_is_producthunt_redirect() -> None:
    assert is_producthunt_redirect("https://www.producthunt.com/r/abc")
    assert not is_producthunt_redirect("https://www.producthunt.com/products/abc")


def test_website_identity_and_canonical() -> None:
    assert website_identity("https://www.producthunt.com/r/AbC") == "producthunt.com/r/abc"
    assert canonical_lead_website("https://www.producthunt.com/r/AbC") == (
        "https://www.producthunt.com/r/AbC"
    )
    assert canonical_lead_website("https://www.acme.com/about") == "acme.com"


def test_is_usable_company_website() -> None:
    assert is_usable_company_website("https://acme.com") is True
    assert is_usable_company_website("https://www.producthunt.com/r/abc") is False
    assert is_usable_company_website("https://www.producthunt.com/products/x") is False
    assert is_usable_company_website("https://blog.cloudflare.com/wallets") is False
    assert is_usable_company_website("https://challenges.cloudflare.com/") is False
    assert is_usable_company_website("https://blog.acme.com") is False
