"""Teacher requests (ID-07, ADR-0046): a student of a shala names their teacher; the link
comes to exist only on the teacher's yes.

A request is not a link: nothing here grants a view of anyone's log. The stored states are
four, and nothing is written when a request runs out: the 7 days are a read-time rule on
`created_at`.

One projection serves the student. Everything a student can observe goes through
`waiting_for_student`, `closing_due`, `ask_state` and `exported_state`, and each of them gives
the same result for `DECLINED` as for `WAITING`: a "no" and a week of silence must look the
same. The teacher's side uses `waiting_for_teacher`.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS

ANSWER_WITHIN = timedelta(days=7)  # the teacher's yes counts only inside it (Q318)
KEEP = timedelta(days=30)  # one row per pair for this long, however it ended (Q317)
MAX_ASKING = 3  # a student's waiting requests, all shalas (Q319)
MAX_WAITING = 100  # waiting requests per teacher


@dataclass(frozen=True, slots=True)
class RequestCaps:
    """Soft, like ID-04's: a race can overshoot by a few."""

    asking: int = MAX_ASKING
    waiting: int = MAX_WAITING
    teachers: int = MAX_TEACHERS  # links + waiting requests, per student
    students: int = MAX_STUDENTS  # links + waiting requests, per teacher


CAPS = RequestCaps()


class RequestState(StrEnum):
    """As stored. `DECLINED` never reaches a student-facing surface."""

    WAITING = "waiting"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    APPROVED = "approved"


class AskState(StrEnum):
    """What the student's tap came to. Every refusal is about the student's own side, except
    `FULL`, which says only "not right now"."""

    CREATED = "created"
    LINKED = "linked"  # already their student
    WAITING = "waiting"  # asked, no answer yet (or a quiet no)
    RECENT = "recent"  # asked in the last 30 days
    TOO_MANY = "too_many"  # the student's own limits
    FULL = "full"  # the teacher's limits


class Closing(StrEnum):
    """The one note that closes a request for the student."""

    CONFIRMED = "confirmed"
    NO_ANSWER = "no_answer"


_OPEN = frozenset({RequestState.WAITING, RequestState.DECLINED})


def _inside(created_at: datetime, now: datetime) -> bool:
    return now < created_at + ANSWER_WITHIN


def waiting_for_student(state: RequestState, created_at: datetime, now: datetime) -> bool:
    """The student's "waiting": a quiet no still waits, so it frees no slot and moves no
    clock."""
    return state in _OPEN and _inside(created_at, now)


def waiting_for_teacher(state: RequestState, created_at: datetime, now: datetime) -> bool:
    """On the teacher's list: not answered yet."""
    return state is RequestState.WAITING and _inside(created_at, now)


def answerable(state: RequestState, created_at: datetime, now: datetime) -> bool:
    """A yes still makes the link: not answered, or a no taken back (Undo, Q320)."""
    return state in _OPEN and _inside(created_at, now)


def kept(created_at: datetime, now: datetime) -> bool:
    """The row still stands for the pair: no new ask yet, whatever its state."""
    return now < created_at + KEEP


def closing_due(
    state: RequestState, created_at: datetime, linked: bool, now: datetime
) -> Closing | None:
    """The note the student is owed now. Confirmed as soon as the link exists; no answer at
    day 7 exactly, whenever the teacher tapped; nothing once the two are linked another way,
    after a withdrawal, or when an approved link was removed again."""
    if state is RequestState.APPROVED:
        return Closing.CONFIRMED if linked else None
    if state in _OPEN and not linked and not _inside(created_at, now):
        return Closing.NO_ANSWER
    return None


def ask_state(
    *,
    linked: bool,
    earlier: tuple[RequestState, datetime] | None,
    now: datetime,
    my_waiting: int,
    my_teachers: int,
    their_waiting: int,
    their_students: int,
    caps: RequestCaps = CAPS,
    still_valid: bool = True,
) -> AskState:
    """Whether a student may ask this teacher now. `earlier` is the pair's own row, if any,
    and `still_valid` whether the student has stayed in its shala since (a rejoin revives
    nothing, so that row no longer waits, but it still blocks a new ask). `my_waiting`
    counts by `waiting_for_student`, `their_waiting` by `waiting_for_teacher`. Waiting
    requests count toward the link caps on both sides (Q319)."""
    if linked:
        return AskState.LINKED
    if earlier is not None and kept(earlier[1], now):
        waits = still_valid and waiting_for_student(*earlier, now)
        return AskState.WAITING if waits else AskState.RECENT
    if my_waiting >= caps.asking or my_teachers + my_waiting >= caps.teachers:
        return AskState.TOO_MANY
    if their_waiting >= caps.waiting or their_students + their_waiting >= caps.students:
        return AskState.FULL
    return AskState.CREATED


def exported_state(mine: bool, state: RequestState, created_at: datetime, now: datetime) -> str:
    """ST-09: the state as its owner may read it. `mine`: I am the student, and the word
    never says the teacher answered no. As the teacher, "declined" is my own action."""
    if state is RequestState.APPROVED:
        return "confirmed"
    if mine:
        if state is RequestState.WITHDRAWN:
            return "withdrawn"
        return "waiting" if waiting_for_student(state, created_at, now) else "no_answer"
    if state is RequestState.DECLINED:
        return "declined"
    return "waiting" if waiting_for_teacher(state, created_at, now) else "closed"


def request_key(id: UUID) -> str:
    """The delivery ledger's dedupe key for a request's closing note."""
    return f"req:{id}"
