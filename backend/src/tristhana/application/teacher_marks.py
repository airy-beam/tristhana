"""A linked teacher marks a new asana for a student (PR-08 Phase 3, ADR-0037). Both adapters
use it. Built with the progression port, the track, a clock and the notifier only, so no
decrypted value is in reach.

One read (the link and the student's view, in one statement), the domain rule, one guarded
write (the link `EXISTS`, `last_event_id` and the position), then one silent note to the
student. The teacher's reply is `Marked(seen, target)` alone: it can't vary with the student's
history, their items or whether the note arrived.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.application.policies import NotAllowed, Principal, can_mark_progression
from tristhana.application.ports.notifications import AsanaMarked, Notifier, Recipient
from tristhana.application.ports.progression import ProgressionRepository
from tristhana.application.ports.storage import Clock
from tristhana.application.ports.teacher_links import NotLinked
from tristhana.application.progression import ProgressionChanged
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.progression import (
    InvalidProgression,
    Position,
    Track,
    celebrations,
    teacher_change,
)


@dataclass(frozen=True, slots=True)
class Marked:
    """What the teacher learns: the position they saw and the one they marked."""

    seen: Position
    target: Position


class MarkForStudent:
    def __init__(
        self, progression: ProgressionRepository, track: Track, clock: Clock, notifier: Notifier
    ) -> None:
        self._progression = progression
        self._track = track
        self._clock = clock
        self._notifier = notifier

    async def execute(
        self, principal: Principal, student_id: UUID, seen: Position, target: Position
    ) -> Marked:
        """Raises `NotLinked`, `NotAllowed` (the port handed back someone else's link), or
        `ProgressionChanged` (the card was out of date: unset, moved on, or a target outside
        the next stops; or a lost compare-and-set). A note that isn't delivered still marks."""
        teacher = principal.account
        found = await self._progression.for_teacher(teacher.id, student_id)
        if found is None:
            raise NotLinked
        link, view = found.link, found.view
        if not can_mark_progression(teacher, link):
            raise NotAllowed
        # The student's today, never the teacher's: a late mark lands on the day it is made.
        on = local_today(self._clock.now(), link.timezone or provisional_zone(link.locale))
        try:
            change = teacher_change(self._track, view.progression, seen, target, on)
        except InvalidProgression:
            raise ProgressionChanged("the card was out of date") from None
        expected = view.progression.last_event_id if view.progression else None
        event = await self._progression.apply(
            link.student_id,
            change,
            expected,
            teacher.id,
            before=seen,
            link_teacher=teacher.id,
        )
        if event is None:
            raise ProgressionChanged("lost the compare-and-set")
        if link.telegram_id is not None:  # a web-only account sees it in My asanas
            found_now = celebrations(self._track, view.earlier, change)
            await self._notifier.tell_asana_marked(  # BLOCKED or FAILED: still marked
                Recipient(link.telegram_id, link.locale),
                teacher.display_name,
                AsanaMarked(event.id, found_now, target),
            )
        return Marked(seen, target)
