"""The simple journey (UI-06): who meets the front door, and what the Menu holds.

Everything is derived from the loaded account (ID-03: roles are data, never stored), so the
Menu costs no read. The one stored fact is `Account.welcomed`: "shown once" cannot be derived,
because a teacher whose students have not joined yet has no activity at all.
"""

from enum import StrEnum

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
    """At most eight rows, plus the quiet one for everyone who has no students and is on no
    shala's staff (Q310; the main shala is a staff one whenever the person is staff anywhere)."""
    on_staff = account.shala is not None and account.shala.staff
    hidden = {
        *(() if account.shala is not None else (MenuItem.CLASSES,)),
        *(() if account.teaches else (MenuItem.STUDENTS,)),
        *((MenuItem.TEACH,) if account.teaches or on_staff else ()),
    }
    return tuple(item for item in MenuItem if item not in hidden)
