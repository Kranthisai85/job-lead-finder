"""Placeholder scrubbing for outbound email drafts."""

from __future__ import annotations

from app.email_queue.placeholders import (
    contains_contact_placeholder,
    resolve_first_name,
    scrub_template_placeholders,
)
from app.email_queue.queue import compose_email_body
from app.ai.types import GeneratedEmail
from app.sender_profile.types import SenderProfile


def test_scrub_replaces_first_name_placeholder() -> None:
    text = scrub_template_placeholders(
        "Hi {{first_name}},\n\nNice product.",
        recipient_name="Priya Sharma",
    )
    assert "{{first_name}}" not in text
    assert text.startswith("Hi Priya,")


def test_scrub_removes_greeting_when_no_name() -> None:
    text = scrub_template_placeholders(
        "Hi {{first_name}},\n\nNice product.",
        recipient_name="there",
    )
    assert "{{first_name}}" not in text
    assert not text.lower().startswith("hi ,")
    assert "Nice product." in text


def test_compose_never_leaves_first_name_placeholder() -> None:
    email = GeneratedEmail(
        subject="Mobile idea",
        opening="Hi {{first_name}},",
        body="I noticed your product.",
        cta="Open to a chat?",
        signature="{{sender_name}}",
        generation_source="ollama",
    )
    body = compose_email_body(
        email,
        profile=SenderProfile(display_name="Kranthi"),
        recipient_name="there",
    )
    assert "{{first_name}}" not in body
    assert contains_contact_placeholder(body) is False
    assert "Kranthi" in body


def test_resolve_first_name_rejects_polluted_titles() -> None:
    assert resolve_first_name("Descontos de Aniversário em Portugal") == ""
    assert resolve_first_name("Ada Lovelace") == "Ada"
