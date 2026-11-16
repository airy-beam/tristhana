"""The simple journey (UI-06): who meets the front door, what the Menu holds, and the next
step the Today tab offers.

Everything is derived from the loaded account (ID-03: roles are data, never stored), so the
Menu costs no read. The one stored fact is `Account.welcomed`: "shown once" cannot be derived,
because a teacher whose students have not joined yet has no activity at all. The next step
(stage 2) needs one read, `JourneyFacts`; nothing is stored for it either: a step is due until
the data it ends in exists.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from tristhana.domain.accounts import Account
from tristhana.domain.days import DayStatus


class MenuItem(StrEnum):
    """The Menu's rows; the definition order is the display order."""

    TODAY = "today"
    PRACTICE = "practice"  # "My practice": opens the Mini App
    MOON = "moon"
    CLASSES = "classes"  # only with a shala
    TEACHER = "teacher"  # "My teacher"
    STUDENTS = "students"  # only with students
    SETTINGS = "settings"
    HELP = "help"
    TEACH = "teach"  # the quiet last row: "For teachers and shalas"


# "Other reason" under Today's third button (T1), in display order. 🧘 and 😌 have their own
# buttons. The screen leaves 🌸 out under `hide_ladies` (WH-01).
OTHER_REASONS: tuple[DayStatus, ...] = (
    DayStatus.MOON,
    DayStatus.LADIES,
    DayStatus.SICK,
    DayStatus.TRAVEL,
    DayStatus.SKIPPED,
)


def active(account: Account, has_days: bool) -> bool:
    """Has done something already: a student, a teacher, a shala or a logged day."""
    return (
        account.teaches or account.main_teacher is not None or account.shala is not None or has_days
    )


def front_door(account: Account, has_days: bool) -> bool:
    """Whether `/start` shows the front door: not seen yet, and nothing done yet. `has_days`
    comes with the write that marks it seen (`AccountRepository.mark_welcomed`)."""
    return not account.welcomed and not active(account, has_days)


def menu_for(account: Account) -> tuple[MenuItem, ...]:
    """At most eight rows, plus the quiet one for everyone without students: a person has either
    "My students" or the way to their first invite, never neither (Q310 as refined: a teacher on
    a shala's staff with no students yet would otherwise have no invite path in the Menu)."""
    hidden = {
        *(() if account.shala is not None else (MenuItem.CLASSES,)),
        *(() if account.teaches else (MenuItem.STUDENTS,)),
        *((MenuItem.TEACH,) if account.teaches else ()),
    }
    return tuple(item for item in MenuItem if item not in hidden)


class NextStep(StrEnum):
    """What the Today tab may offer next; the definition order is the offer order."""

    ADD_CLASS = "add_class"
    INVITE_SHALA_STUDENTS = "invite_shala_students"
    INVITE_STUDENT = "invite_student"
    REMINDER = "reminder"
    POSITION = "position"  # where the practice ends


# Q334: "invite your first student" is offered only while the invite link is this fresh. A
# link older than that with nobody on it was most likely opened out of curiosity.
INVITE_FRESH_DAYS = 30


@dataclass(frozen=True, slots=True)
class OwnedShala:
    """A shala the person owns, as far as the steps need it."""

    id: UUID
    classes: int
    students: int


@dataclass(frozen=True, slots=True)
class JourneyFacts:
    """What `next_steps` needs beyond the loaded account, read in one statement."""

    has_days: bool = False  # any logged day, whatever its status
    reminder_answered: bool = False  # the practice reminder was chosen: "yes" or "no"
    position_set: bool = False  # where the practice ends ("standing only" is an answer)
    invite_made_on: date | None = None  # the teacher invite link's date (UTC); None: no link
    owned: tuple[OwnedShala, ...] = ()  # oldest first


@dataclass(frozen=True, slots=True)
class Step:
    kind: NextStep
    shala_id: UUID | None = None  # the owned shala a shala step is about


def next_steps(account: Account, facts: JourneyFacts, today: date) -> tuple[Step, ...]:
    """Every step still due, in offer order; at most one of a kind. The screen shows the first.

    Before the first logged day a student gets none: the day card is the step. A shala owner
    is never offered the teacher's invite, the shala steps cover it (Q334). A shala step names
    the oldest shala it applies to.
    """
    no_class = next((s for s in facts.owned if s.classes == 0), None)
    no_student = next((s for s in facts.owned if s.classes > 0 and s.students == 0), None)
    made = facts.invite_made_on
    invite = (
        made is not None
        and (today - made).days <= INVITE_FRESH_DAYS
        and not account.teaches
        and not facts.owned
    )
    due = {
        NextStep.ADD_CLASS: no_class is not None,
        NextStep.INVITE_SHALA_STUDENTS: no_student is not None,
        NextStep.INVITE_STUDENT: invite,
        NextStep.REMINDER: facts.has_days and not facts.reminder_answered,
        NextStep.POSITION: facts.has_days and not facts.position_set,
    }
    shala = {
        NextStep.ADD_CLASS: no_class,
        NextStep.INVITE_SHALA_STUDENTS: no_student,
    }
    return tuple(
        Step(kind, found.id if (found := shala.get(kind)) is not None else None)
        for kind in NextStep
        if due[kind]
    )
