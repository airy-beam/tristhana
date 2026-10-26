"""When notifications are due (MD-03 moon reminders, PR-10 the daily practice reminder).

Pure rules: the tick asks "what is due right now?" for each account, so DST and zone
changes need no stored schedule. Instants are UTC; send times are the recipient's wall
clock in their IANA zone (ADR-0005). The provisional zone is never used here.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tristhana.domain.moon import MoonDay
from tristhana.domain.rest_days import WEEKDAYS as WEEKDAYS
from tristhana.domain.rest_days import Weekdays

MOON_OFFSETS = frozenset({1, 3, 7})
GRACE = timedelta(hours=3)  # a reminder more than this late is dropped, not sent at 4 am
SEND_TIMES = (time(7), time(12), time(19), time(21))
PRACTICE_TIMES = tuple(time(h) for h in (9, 10, 12, 18, 20, 21))  # ashtanga-expert
UNANSWERED_LIMIT = 10  # reminded days left unlogged in a row before one note and a pause
COPIED_DATE_AFTER = timedelta(days=14)  # older: "same as last time" says which day it was


@dataclass(frozen=True, slots=True)
class QuietHours:
    start: time
    end: time  # may wrap midnight; start == end means no quiet hours

    def contains(self, at: time) -> bool:
        if self.start == self.end:
            return False
        if self.start < self.end:
            return self.start <= at < self.end
        return at >= self.start or at < self.end


@dataclass(frozen=True, slots=True)
class MoonReminders:
    offsets: frozenset[int]  # days before; empty = off
    at: time

    @property
    def on(self) -> bool:
        return bool(self.offsets)


@dataclass(frozen=True, slots=True)
class PracticeReminders:
    on: bool | None  # None = never chosen: off, and the one-time offer may still show
    at: time
    days: frozenset[int]  # ISO weekdays

    @property
    def enabled(self) -> bool:
        return self.on is True


# Opt-in; Saturday off as in Mysore (owner, 2026-10-19).
PRACTICE_DEFAULT = PracticeReminders(None, time(10), frozenset({1, 2, 3, 4, 5, 7}))


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    moon: MoonReminders
    quiet: QuietHours
    daily_cap: int
    practice: PracticeReminders = PRACTICE_DEFAULT


DEFAULTS = NotificationSettings(
    moon=MoonReminders(frozenset({7, 1}), time(19)),  # owner: 7 + 1, 3 optional
    quiet=QuietHours(time(22), time(7)),
    daily_cap=3,
)


def reminder_days(days_off: Weekdays | None) -> frozenset[int]:
    """Practice reminder days that follow the day off (PR-09): never chosen keeps the
    Mysore default (Saturday off); no fixed day off means every day."""
    if days_off is None:
        return PRACTICE_DEFAULT.days
    return WEEKDAYS - days_off


def defaults_for(
    days_off: Weekdays | None, base: "NotificationSettings | None" = None
) -> "NotificationSettings":
    """The defaults for one account: its practice days are the reminder days (PR-09: one
    setting, the day off; reminder days are no longer chosen separately)."""
    base = base or DEFAULTS
    days = reminder_days(days_off)
    if days == base.practice.days:
        return base
    return replace(base, practice=replace(base.practice, days=days))


@dataclass(frozen=True, slots=True)
class DayOffQuestion:
    weekday: int  # the one day reminders skip
    reminders_on: bool


def day_off_question(
    days_off: Weekdays | None, dismissed: bool, settings: NotificationSettings
) -> DayOffQuestion | None:
    """The one-time "is that your day off?" (PR-09): only while the day off was never
    chosen nor the question dismissed, and the reminder days miss exactly one weekday."""
    if days_off is not None or dismissed:
        return None
    gaps = WEEKDAYS - settings.practice.days
    if len(gaps) != 1:
        return None
    return DayOffQuestion(next(iter(gaps)), settings.practice.enabled)


def default_practice_time(tapped: time) -> time:
    """The reminder time for someone who just accepted the offer after logging today's
    practice: morning practitioners get 10:00, people who log after 14:00 get 20:00."""
    return time(10) if tapped < time(14) else time(20)


class InvalidSettings(ValueError):
    pass


def _check_grid(at: time) -> None:
    if at.second or at.microsecond or at.minute % 15:
        raise InvalidSettings("send time must be on a 15-minute grid")


def check_settings(settings: NotificationSettings) -> NotificationSettings:
    if not settings.moon.offsets <= MOON_OFFSETS:
        raise InvalidSettings("moon offsets must be among 1, 3, 7")
    at = settings.moon.at
    _check_grid(at)
    practice = settings.practice
    if not practice.days or not practice.days <= WEEKDAYS:
        raise InvalidSettings("practice days must be 1-7, at least one")
    _check_grid(practice.at)
    if practice.enabled and settings.quiet.contains(practice.at):
        raise InvalidSettings("the practice reminder falls in quiet hours")
    if not 1 <= settings.daily_cap <= 10:
        raise InvalidSettings("daily cap must be 1-10")
    if settings.moon.on and settings.quiet.contains(at):
        raise InvalidSettings("the send time falls in quiet hours")
    return settings


def send_instant(local_date: date, at: time, zone: str) -> datetime:
    """The UTC instant of `at` on `local_date` in `zone`. In a DST gap the wall clock moves
    forward (02:30 → 03:30); an ambiguous time takes its first occurrence."""
    return datetime.combine(local_date, at, ZoneInfo(zone)).astimezone(UTC)


def moon_key(moon_date: date, days_before: int) -> str:
    return f"moon:{moon_date.isoformat()}:{days_before}"


def practice_key(local_date: date) -> str:
    return f"practice:{local_date.isoformat()}"


def pause_key(local_date: date) -> str:
    """The long-silence note: its own key, so it ends a run of unanswered reminders."""
    return f"practice-pause:{local_date.isoformat()}"


@dataclass(frozen=True, slots=True)
class DueReminder:
    key: str
    moon_day: MoonDay
    days_before: int
    local_date: date  # the recipient's date it is sent on


@dataclass(frozen=True, slots=True)
class Candidate:
    """One account's inputs for the tick."""

    zone: str
    settings: NotificationSettings
    moon_days: tuple[MoonDay, ...]  # dates of the followed calendar's location
    sent_keys: frozenset[str] = field(default_factory=frozenset[str])
    sent_today: int = 0  # notifications already delivered on the recipient's local today
    logged: frozenset[date] = field(default_factory=frozenset[date])  # recent logged days
    practice_sent: tuple[date, ...] = ()  # recent days a practice reminder went out for
    practice_paused: tuple[date, ...] = ()  # recent days the long-silence note went out
    paused: frozenset[date] = field(default_factory=frozenset[date])  # covered by a period


def due_moon_reminders(now: datetime, c: Candidate) -> list[DueReminder]:
    """Moon reminders due at `now` (UTC). A moon day D of the followed calendar is applied
    as the same date in the recipient's zone (as people do when following Mysuru abroad);
    the k-days-before reminder fires at `settings.moon.at` on D - k, within GRACE, outside
    quiet hours, at most once per key, and within the daily cap (day-before first)."""
    settings = c.settings
    if not settings.moon.on:
        return []
    local_now = now.astimezone(ZoneInfo(c.zone))
    if settings.quiet.contains(local_now.time().replace(tzinfo=None)):
        return []
    due: list[DueReminder] = []
    room = settings.daily_cap - c.sent_today
    for k in sorted(settings.moon.offsets):
        for day in c.moon_days:
            if room <= 0:
                return due
            if day.date <= local_now.date():
                continue
            key = moon_key(day.date, k)
            send_at = send_instant(day.date - timedelta(days=k), settings.moon.at, c.zone)
            if key in c.sent_keys or not send_at <= now < send_at + GRACE:
                continue
            due.append(DueReminder(key, day, k, local_now.date()))
            room -= 1
    return due


def sent_today_count(local_dates: Iterable[date], today: date) -> int:
    return sum(1 for d in local_dates if d == today)


@dataclass(frozen=True, slots=True)
class DuePractice:
    key: str
    local_date: date  # the day it asks about (and is sent on)
    pause: bool  # the long-silence note instead of a reminder: then reminders turn off


def due_practice_reminder(now: datetime, c: Candidate, picked: int = 0) -> DuePractice | None:
    """The practice reminder due at `now` (UTC), if any: at `practice.at` on a chosen
    weekday, within GRACE, outside quiet hours, never for a logged day or a moon day of the
    followed calendar, within the daily cap shared with moon reminders (`picked` = moon
    reminders already chosen this tick). Yesterday is checked too: a late slot's grace may
    cross midnight (that reminder is about, and counted on, yesterday: only possible with
    custom quiet hours that let a slot run past midnight). After UNANSWERED_LIMIT reminded
    days in a row stayed unlogged, the reminder becomes one gentle note (`pause`)."""
    practice = c.settings.practice
    if not practice.enabled:
        return None
    zone = ZoneInfo(c.zone)
    local_now = now.astimezone(zone)
    if c.settings.quiet.contains(local_now.time().replace(tzinfo=None)):
        return None
    if c.sent_today + picked >= c.settings.daily_cap:
        return None
    moon_dates = {d.date for d in c.moon_days}
    for day in (local_now.date(), local_now.date() - timedelta(days=1)):
        send_at = send_instant(day, practice.at, c.zone)
        if not send_at <= now < send_at + GRACE:
            continue
        if (
            day.isoweekday() not in practice.days
            or day in c.logged
            or day in c.paused
            or day in moon_dates
            or practice_key(day) in c.sent_keys
            or pause_key(day) in c.sent_keys
        ):
            return None
        if _silent(c, day):
            return DuePractice(pause_key(day), day, pause=True)
        return DuePractice(practice_key(day), day, pause=False)
    return None


def _silent(c: Candidate, day: date) -> bool:
    """The last UNANSWERED_LIMIT reminders before `day` (since the last pause note, so
    turning reminders back on starts a fresh count) all left their day unlogged. A date
    covered by a rest period counts as answered, and one after the oldest counted reminder
    resets the run: starting a pause is an answer (WH-01)."""
    since = max((d for d in c.practice_paused if d < day), default=None)
    before = sorted(
        (d for d in c.practice_sent if d < day and (since is None or d > since)), reverse=True
    )[:UNANSWERED_LIMIT]
    if len(before) < UNANSWERED_LIMIT or any(d in c.logged for d in before):
        return False
    oldest = before[-1]
    return not any(oldest <= d < day for d in c.paused)


@dataclass(frozen=True, slots=True)
class StoredSettings:
    """The settings row as stored: None = "the default" (so later default changes apply)."""

    moon_offsets: frozenset[int] | None = None
    moon_at: time | None = None
    quiet_start: time | None = None  # quiet hours are a pair: both set or both None
    quiet_end: time | None = None
    daily_cap: int | None = None
    practice_on: bool | None = None  # None = never chosen
    practice_at: time | None = None


def effective(stored: StoredSettings, defaults: NotificationSettings) -> NotificationSettings:
    quiet = (
        QuietHours(stored.quiet_start, stored.quiet_end)
        if stored.quiet_start is not None and stored.quiet_end is not None
        else defaults.quiet
    )
    return NotificationSettings(
        moon=MoonReminders(
            stored.moon_offsets if stored.moon_offsets is not None else defaults.moon.offsets,
            stored.moon_at or defaults.moon.at,
        ),
        quiet=quiet,
        daily_cap=stored.daily_cap or defaults.daily_cap,
        practice=PracticeReminders(
            stored.practice_on,
            stored.practice_at or defaults.practice.at,
            defaults.practice.days,  # the practice days (the day off decides them)
        ),
    )


class _Keep:
    def __repr__(self) -> str:
        return "KEEP"


KEEP = _Keep()


@dataclass(frozen=True, slots=True)
class NotificationPatch:
    """A partial change (ADR-0021): KEEP = not sent, None = back to the default."""

    moon_offsets: frozenset[int] | _Keep | None = KEEP
    moon_at: time | _Keep | None = KEEP
    quiet: QuietHours | _Keep | None = KEEP  # a pair
    daily_cap: int | _Keep | None = KEEP
    practice_on: bool | _Keep | None = KEEP
    practice_at: time | _Keep | None = KEEP

    def columns(self) -> dict[str, object]:
        """The stored columns this patch writes (only those sent)."""
        out: dict[str, object] = {}
        for name in (
            "moon_offsets",
            "moon_at",
            "daily_cap",
            "practice_on",
            "practice_at",
        ):
            value = getattr(self, name)
            if not isinstance(value, _Keep):
                out[name] = value
        if not isinstance(self.quiet, _Keep):
            out["quiet_start"] = self.quiet.start if self.quiet else None
            out["quiet_end"] = self.quiet.end if self.quiet else None
        return out


def apply_patch(stored: StoredSettings, patch: NotificationPatch) -> StoredSettings:
    return replace(stored, **patch.columns())  # type: ignore[arg-type]
