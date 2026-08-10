from __future__ import annotations

from app.company_profile.names import clean_company_display_name, prefer_company_name


def test_clean_company_display_name_strips_colon_tagline() -> None:
    assert (
        clean_company_display_name(
            "Pesterly: somebody has to nag. It doesn't have to be you."
        )
        == "Pesterly"
    )


def test_clean_company_display_name_strips_em_dash_subtitle() -> None:
    assert clean_company_display_name("Zephyrax — Monster Battle Arena") == "Zephyrax"


def test_prefer_seed_when_profile_polluted() -> None:
    assert (
        prefer_company_name(
            seed_name="Pesterly",
            profile_name="Pesterly: somebody has to nag. It doesn't have to be you.",
        )
        == "Pesterly"
    )
