"""Authorization lives here, never in handlers or the UI (CLAUDE.md).

A `Principal` is the authenticated caller. Today every operation acts on the caller's own
account; reads across accounts (teachers, ST-06) get a named policy function here.
"""

from dataclasses import dataclass

from tristhana.domain.accounts import Account


@dataclass(frozen=True, slots=True)
class Principal:
    account: Account


def can_view_check_ins(viewer: Account, student: Account) -> bool:
    """Check-ins are the student's own (ADR-0024): no one else sees them, not even whether
    one exists. ST-06 may add a per-teacher opt-in here, off by default."""
    return viewer.id == student.id
