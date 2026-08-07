"""Strict outbound email queue status transitions (Step 38)."""

from __future__ import annotations

from app.email_queue.types import EmailQueueStatus

# Allowed directed edges only. PENDING never reaches SENT directly.
ALLOWED_TRANSITIONS: frozenset[tuple[EmailQueueStatus, EmailQueueStatus]] = frozenset(
    {
        (EmailQueueStatus.PENDING, EmailQueueStatus.APPROVED),
        (EmailQueueStatus.PENDING, EmailQueueStatus.SKIPPED),
        (EmailQueueStatus.APPROVED, EmailQueueStatus.READY_TO_SEND),
        (EmailQueueStatus.READY_TO_SEND, EmailQueueStatus.SENT),
        (EmailQueueStatus.READY_TO_SEND, EmailQueueStatus.FAILED),
    }
)


class InvalidTransitionError(ValueError):
    """Raised when a status change is not in the allowed transition set."""

    def __init__(
        self,
        *,
        item_id: str,
        current: EmailQueueStatus,
        target: EmailQueueStatus,
    ) -> None:
        self.item_id = item_id
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition for '{item_id}': {current.value} → {target.value}")


def can_transition(current: EmailQueueStatus, target: EmailQueueStatus) -> bool:
    return (current, target) in ALLOWED_TRANSITIONS


def assert_transition_allowed(
    *,
    item_id: str,
    current: EmailQueueStatus,
    target: EmailQueueStatus,
) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(item_id=item_id, current=current, target=target)
