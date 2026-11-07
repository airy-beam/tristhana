"""Authorization lives here, never in handlers or the UI (CLAUDE.md).

A `Principal` is the authenticated caller. Today every operation acts on the caller's own
account; reads across accounts (teachers, ST-06) get a named policy function here. A teacher
link (ID-04) exposes names only: the `can_view_*` below stay owner-only until ST-06.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.domain.accounts import Account


class NotAllowed(Exception):
    """A policy said no."""


@dataclass(frozen=True, slots=True)
class Principal:
    account: Account


def can_view_check_ins(viewer: Account, student: Account) -> bool:
    """Check-ins are the student's own (ADR-0024): no one else sees them, not even whether
    one exists. ST-06 may add a per-teacher opt-in here, off by default."""
    return viewer.id == student.id


def can_view_diary(viewer: Account, student: Account) -> bool:
    """Diary notes are the student's own (ADR-0025): no one else reads them or learns that
    one exists. ST-06 may add per-entry sharing here, off by default."""
    return viewer.id == student.id


def can_view_progression(viewer: Account, student: Account) -> bool:
    """Progression is the student's own for now (ADR-0026). ST-06 adds linked teachers here:
    the position and the given asanas, never a change back or an undo."""
    return viewer.id == student.id


def can_export(viewer: Account, owner: Account) -> bool:
    """An export opens every seal (🌸, diary): only ever the owner's own (ST-09)."""
    return viewer.id == owner.id


def can_delete_account(viewer: Account, owner: Account) -> bool:
    """Only the owner deletes an account (ST-09); no admin path today."""
    return viewer.id == owner.id


def can_unlink(actor: Account, student_id: UUID, teacher_id: UUID) -> bool:
    """Either side of a link can remove it (ID-04)."""
    return actor.id in (student_id, teacher_id)


def can_choose_primary(actor: Account, student_id: UUID) -> bool:
    """The main teacher is the student's own choice; a teacher never learns of it (ID-04)."""
    return actor.id == student_id


def can_manage_invite(actor: Account, owner: Account) -> bool:
    """An invite is its owner's to show and rotate (ID-04)."""
    return actor.id == owner.id
