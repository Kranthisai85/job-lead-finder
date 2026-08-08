"""Sender profile package."""

from app.sender_profile.service import SenderProfileService
from app.sender_profile.types import (
    SENDER_NAME_PLACEHOLDER,
    SenderProfile,
    SenderProfileUpdate,
    build_signature_block,
    finalize_body_for_send,
)

__all__ = [
    "SENDER_NAME_PLACEHOLDER",
    "SenderProfile",
    "SenderProfileService",
    "SenderProfileUpdate",
    "build_signature_block",
    "finalize_body_for_send",
]
