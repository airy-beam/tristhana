"""Authorization lives here, never in handlers or the UI (CLAUDE.md).

A `Principal` is the authenticated caller. Today every operation acts on the caller's own
account; reads across accounts get a named policy function here. A teacher sees only what the
link's consent names (ST-06, ADR-0031): `can_view_activity` and `can_view_last_asana`. The
owner-only `can_view_*` below get no link argument.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.application.ports.teacher_view import StudentLink
from tristhana.domain.accounts import Account


class NotAllowed(Exception):
    """A policy said no."""


@dataclass(frozen=True, slots=True)
class Principal:
    account: Account


def can_view_check_ins(viewer: Account, student: Account) -> bool:
    """Check-ins are the student's own (ADR-0024): no one else sees them, not even whether
    one exists. A per-teacher opt-in would need its own consent and ADR (ADR-0031)."""
    return viewer.id == student.id


def can_view_diary(viewer: Account, student: Account) -> bool:
    """Diary notes are the student's own (ADR-0025): no one else reads them or learns that
    one exists. Per-entry sharing would need its own consent and ADR (ADR-0031)."""
    return viewer.id == student.id


def can_view_progression(viewer: Account, student: Account) -> bool:
    """Events and milestone items are the student's own (ADR-0026). A teacher gets the position
    alone, through `can_view_last_asana` (ST-06)."""
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


def can_view_activity(viewer: Account, link: StudentLink) -> bool:
    """A link's teacher sees its projected days (ST-06). Rights go one hop and one way, so the
    direction matters in a cycle."""
    return link.teacher_id == viewer.id


def can_view_last_asana(viewer: Account, link: StudentLink) -> bool:
    """A link's teacher sees the current position, never the events behind it (ST-06)."""
    return link.teacher_id == viewer.id


def can_view_milestones(viewer: Account, student: Account) -> bool:
    """Milestones are the student's own: the consent doesn't name them (Q59)."""
    return viewer.id == student.id
