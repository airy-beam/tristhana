"""When notifications are due (MD-03 moon reminders; PR-10 will add the practice reminder).

Pure rules: the tick asks "what is due right now?" for each account, so DST and zone
changes need no stored schedule. Instants are UTC; send times are the recipient's wall
clock in their IANA zone (ADR-0005). The provisional zone is never used here.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tristhana.domain.moon import MoonDay

MOON_OFFSETS = frozenset({1, 3, 7})
GRACE = timedelta(hours=3)  # a reminder more than this late is dropped, not sent at 4 am
SEND_TIMES = (time(7), time(12), time(19), time(21))


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
class NotificationSettings:
    moon: MoonReminders
    quiet: QuietHours
    daily_cap: int


DEFAULTS = NotificationSettings(
    moon=MoonReminders(frozenset({7, 1}), time(19)),  # owner: 7 + 1, 3 optional
    quiet=QuietHours(time(22), time(7)),
    daily_cap=3,
)


class InvalidSettings(ValueError):
    pass


def check_settings(settings: NotificationSettings) -> NotificationSettings:
    if not settings.moon.offsets <= MOON_OFFSETS:
        raise InvalidSettings("moon offsets must be among 1, 3, 7")
    at = settings.moon.at
    if at.second or at.microsecond or at.minute % 15:
        raise InvalidSettings("send time must be on a 15-minute grid")
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
