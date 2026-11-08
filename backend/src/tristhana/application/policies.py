"""Authorization lives here, never in handlers or the UI (CLAUDE.md).

A `Principal` is the authenticated caller. Today every operation acts on the caller's own
account; reads across accounts get a named policy function here. A teacher sees only what the
link's consent names (ST-06, ADR-0031): `can_view_activity` and `can_view_last_asana`. The
owner-only `can_view_*` below get no link argument.

Shala policies (SC-01, ADR-0033) take the caller's `Membership`, read in the same statement as
the write; None = not a member, which the use cases turn into `NotFound`, never `NotAllowed`,
so shala ids can't be probed. A shala membership never grants any of the teacher policies.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.application.ports.teacher_view import StudentLink
from tristhana.domain.accounts import Account
from tristhana.domain.shalas import Membership, ShalaRole, grantable


class NotAllowed(Exception):
    """A policy said no."""


class NotFound(Exception):
    """Not there, or not a member: the two look the same from outside."""


@dataclass(frozen=True, slots=True)
class Principal:
    account: Account


def can_manage_calendar_feed(actor: Account, owner: Account) -> bool:
    """SC-06: a calendar link is its owner's alone (show, create, rotate, turn off)."""
    return actor.id == owner.id


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


def can_view_shala(actor: Membership | None) -> bool:
    """Any member sees the card: the shala, its staff and their roles."""
    return actor is not None


def can_view_shala_students(actor: Membership | None) -> bool:
    """Staff see student names; students never see each other (Q106)."""
    return actor is not None and actor.staff


def can_show_join_link(actor: Membership | None) -> bool:
    return actor is not None and actor.staff


def _manages(actor: Membership | None) -> bool:
    return actor is not None and actor.staff and (actor.owner or ShalaRole.ADMIN in actor.roles)


def can_edit_shala(actor: Membership | None) -> bool:
    return _manages(actor)


_SCHEDULE_ROLES = frozenset({ShalaRole.ADMIN, ShalaRole.TEACHER, ShalaRole.OFFICE})


def can_view_schedule(actor: Membership | None) -> bool:
    """SC-02: any member reads the schedule."""
    return actor is not None


def can_view_private_classes(actor: Membership | None) -> bool:
    """1:1 classes are for staff only (Q121): their titles may name a person."""
    return actor is not None and actor.staff


def can_manage_schedule(actor: Membership | None) -> bool:
    """Classes, exceptions, closures and swaps (Q118); the day off and the moon policy stay
    with `can_edit_shala`."""
    return (
        actor is not None and actor.staff and (actor.owner or bool(actor.roles & _SCHEDULE_ROLES))
    )


def can_rotate_join_link(actor: Membership | None) -> bool:
    return _manages(actor)


def can_delete_shala(actor: Membership | None) -> bool:
    return actor is not None and actor.owner


def can_invite_staff(actor: Membership | None, role: ShalaRole) -> bool:
    """A role the inviter may grant: managers are made by the owner only."""
    return actor is not None and role in grantable(actor)


def can_set_roles(
    actor: Membership | None, target: Membership, roles: frozenset[ShalaRole]
) -> bool:
    """Never on the owner or a student; a manager's roles only by the owner."""
    if actor is None or not target.staff or target.owner:
        return False
    allowed = grantable(actor)
    if not allowed or not roles <= allowed:
        return False
    return actor.owner or ShalaRole.ADMIN not in target.roles


def can_remove_staff(actor: Membership | None, target: Membership, *, own: bool) -> bool:
    """The owner removes anyone else, a manager non-managers; anyone leaves but the owner."""
    if actor is None or not target.staff or target.owner:
        return False
    if own:
        return True
    return actor.owner or (
        actor.staff and ShalaRole.ADMIN in actor.roles and ShalaRole.ADMIN not in target.roles
    )


def can_remove_student(actor: Membership | None, *, own: bool) -> bool:
    """A student leaves; the owner, a manager or the front desk removes a student."""
    if actor is None:
        return False
    if own:
        return actor.student
    return actor.staff and (actor.owner or bool(actor.roles & {ShalaRole.ADMIN, ShalaRole.OFFICE}))
