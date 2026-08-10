"""Sender profile + signature helper tests."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.sender_profile import SenderProfileDocument
from app.sender_profile.service import SenderProfileService
from app.sender_profile.types import (
    SenderProfile,
    SenderProfileUpdate,
    build_signature_block,
    finalize_body_for_send,
)


@pytest.fixture()
async def profile_db() -> AsyncIterator[Any]:
    client = AsyncMongoMockClient()
    database = client["lead_finder_profile_test"]
    await init_beanie(database=database, document_models=[SenderProfileDocument])
    yield database
    await SenderProfileDocument.delete_all()
    client.close()


def test_build_signature_block_with_links() -> None:
    block = build_signature_block(
        SenderProfile(
            display_name="Kranthi Sai",
            linkedin_url="https://linkedin.com/in/kranthi",
            github_url="https://github.com/kranthi",
            phone_number="+91 98765 43210",
        )
    )
    assert block == (
        "Best regards,\n"
        "Kranthi Sai\n"
        "LinkedIn: https://linkedin.com/in/kranthi\n"
        "GitHub: https://github.com/kranthi\n"
        "WhatsApp: +91 98765 43210\n"
        "https://wa.me/919876543210"
    )


def test_finalize_body_replaces_placeholder() -> None:
    profile = SenderProfile(
        display_name="Kranthi Sai",
        linkedin_url="https://linkedin.com/in/kranthi",
        github_url="https://github.com/kranthi",
        phone_number="+919876543210",
    )
    body = finalize_body_for_send(
        "Hi Ada,\n\nThanks.\n\nBest regards,\n{{sender_name}}",
        profile,
    )
    assert "{{sender_name}}" not in body
    assert "https://wa.me/919876543210" in body
    assert body.endswith(
        "Best regards,\nKranthi Sai\nLinkedIn: https://linkedin.com/in/kranthi\n"
        "GitHub: https://github.com/kranthi\n"
        "WhatsApp: +919876543210\n"
        "https://wa.me/919876543210"
    )


@pytest.mark.asyncio
async def test_sender_profile_round_trip(profile_db: Any) -> None:
    service = SenderProfileService()
    empty = await service.get_profile()
    assert empty.display_name == ""

    saved = await service.update_profile(
        SenderProfileUpdate(
            display_name="  Kranthi Sai  ",
            linkedin_url=" https://linkedin.com/in/kranthi ",
            github_url=" https://github.com/kranthi ",
            phone_number=" +91 98765 43210 ",
        )
    )
    assert saved.display_name == "Kranthi Sai"
    assert saved.linkedin_url == "https://linkedin.com/in/kranthi"
    assert saved.github_url == "https://github.com/kranthi"
    assert saved.phone_number == "+91 98765 43210"

    loaded = await service.get_profile()
    assert loaded == saved
