"""Export of one's own data (ST-09, ADR-0027): a snapshot of every stored fact, as versioned
JSON (`data.json`) and spreadsheet tables (`days.csv`, `rest_periods.csv`, `progression.csv`).

The owner gets true values: a sealed rest opens to 🌸 or rest, a period to its kind, a note to
its text. An unreadable seal (lost key, ADR-0016) stays in, says rest and never guesses 🌸.
Derived days (day off, moon days, pause coverage: ADR-0022/0023) are not rows; their inputs
are. Keys and codes are English machine names; `*_name`/`*_label` come from `ExportLabels`
in the account's language. Internal guards (dedupe keys, CAS ids, hints) never leave."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from tristhana.domain.accounts import Account
from tristhana.domain.check_in import CheckIn
from tristhana.domain.days import DayStatus
from tristhana.domain.notifications import NotificationSettings
from tristhana.domain.practice import Practice, PracticeLength
from tristhana.domain.progression import EventKind, Position, Progression, ProgressionEvent
from tristhana.domain.rest_days import Weekdays

SCHEMA = "tristhana.export/1"  # bumped on any breaking change
EXPORT_EVERY = timedelta(minutes=10)  # one export per account per window (Q5)
MAX_BYTES = 45 * 1024 * 1024  # under Telegram's 50 MB upload limit
REMINDER_DAYS = 60  # the delivery ledger is exported for this many days (Q7)

# Export vocabulary: "skipped" was never shown to anyone (PR-01: "No practice").
_STATUS = {s: s.value for s in DayStatus} | {DayStatus.SKIPPED: "no_practice"}


class MarkedBy(StrEnum):
    """Who marked a progression event: never a name or an id (a teacher's account may be
    gone; the export is the student's)."""

    SELF = "self"
    TEACHER = "teacher"
    UNKNOWN = "unknown"  # the marking account was deleted


@dataclass(frozen=True, slots=True)
class ExportIdentity:
    provider: str
    id: str
    linked_at: datetime


@dataclass(frozen=True, slots=True)
class ExportDay:
    local_date: date
    status: DayStatus  # the opened value; REST when `unreadable`
    timezone: str | None  # the zone "today" was computed in; None = provisional
    unreadable: bool = False


@dataclass(frozen=True, slots=True)
class ExportPeriod:
    start: date
    end: date  # inclusive
    kind: DayStatus | None  # None = the seal can't be opened

    @property
    def unreadable(self) -> bool:
        return self.kind is None


@dataclass(frozen=True, slots=True)
class ExportPractice:
    local_date: date
    practice: Practice


@dataclass(frozen=True, slots=True)
class ExportCheckIn:
    local_date: date
    check_in: CheckIn


@dataclass(frozen=True, slots=True)
class ExportNote:
    local_date: date
    text: str | None  # None = the seal can't be opened

    @property
    def unreadable(self) -> bool:
        return self.text is None


@dataclass(frozen=True, slots=True)
class ExportReminder:
    category: str  # moon | practice
    local_date: date
    status: str  # claimed | sent | failed | blocked


@dataclass(frozen=True, slots=True)
class ExportEvent:
    event: ProgressionEvent
    marked_by: MarkedBy
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the person owns, already opened, read in one transaction."""

    account: Account
    identities: tuple[ExportIdentity, ...]
    settings: NotificationSettings  # effective values
    moon_city: str  # resolved slug
    moon_city_default: bool  # never chosen: the default city
    catalog_version: str
    days: tuple[ExportDay, ...]
    periods: tuple[ExportPeriod, ...]
    practices: tuple[ExportPractice, ...]
    check_ins: tuple[ExportCheckIn, ...]
    notes: tuple[ExportNote, ...]
    progression: Progression | None
    events: tuple[ExportEvent, ...]  # oldest first
    reminders: tuple[ExportReminder, ...]
    exported_at: datetime  # UTC


@dataclass(frozen=True, slots=True)
class ExportLabels:
    """Readable names in the account's language, filled by the application from Fluent and
    the catalog (the domain stays free of I/O)."""

    status: Callable[[str], str]  # export status code (rest, ladies, no_practice, …)
    position: Callable[[Position], str]
    stop: Callable[[str, str], str]  # (series, key) -> asana name
    item: Callable[[str], str]  # milestone item key -> name
    kind: Callable[[EventKind, str], str]  # (kind, item label or "")
    length: Callable[[PracticeLength], str]
    unreadable_rest: str


def status_code(status: DayStatus) -> str:
    return _STATUS[status]


def check_rate(last: datetime | None, now: datetime) -> timedelta | None:
    """None = an export may go now; else how long to wait (never more than the window, even
    if the clock moved back)."""
    if last is None:
        return None
    wait = EXPORT_EVERY - (now - last)
    if wait <= timedelta(0):
        return None
    return min(wait, EXPORT_EVERY)


def export_file_name(local: date) -> str:
    """Named after the person's local date (the caption's date too)."""
    return f"tristhana-export-{local.isoformat()}.zip"


# --- JSON ---------------------------------------------------------------------------------


def to_json(s: Snapshot, labels: ExportLabels) -> dict[str, Any]:
    """JSON-ready values only (str, int, bool, None, lists and dicts of them)."""
    return {
        "schema": SCHEMA,
        "exported_at": _instant(s.exported_at),
        "catalog_version": s.catalog_version,
        "account": _account(s),
        "identities": [
            {"provider": i.provider, "id": i.id, "linked_at": _instant(i.linked_at)}
            for i in s.identities
        ],
        "notification_settings": _settings(s.settings),
        "days": [
            {
                "date": d.local_date.isoformat(),
                "status": _day_code(d),
                "status_label": _day_label(d, labels),
                "timezone": d.timezone,
                "unreadable": d.unreadable,
            }
            for d in s.days
        ],
        "rest_periods": [
            {
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
                "kind": status_code(p.kind) if p.kind else None,
                "kind_label": _period_label(p, labels),
                "unreadable": p.unreadable,
            }
            for p in s.periods
        ],
        "practices": [_practice(p, labels) for p in s.practices],
        "check_ins": [
            {"date": c.local_date.isoformat(), "slot": c.check_in.slot} | _check_in(c.check_in)
            for c in s.check_ins
        ],
        "diary": [
            {"date": n.local_date.isoformat(), "text": n.text, "unreadable": n.unreadable}
            for n in s.notes
        ],
        "progression": _progression(s.progression, labels),
        "progression_events": [_event(e, labels) for e in s.events],
        "reminders": [
            {"category": r.category, "date": r.local_date.isoformat(), "status": r.status}
            for r in s.reminders
        ],
    }


def _account(s: Snapshot) -> dict[str, object]:
    a = s.account
    return {
        "id": str(a.id),
        "display_name": a.display_name,
        "name_from_telegram": not a.name_custom,
        "locale": a.locale,
        "locale_from_telegram": not a.locale_custom,
        "timezone": a.timezone,
        "moon_city": {"slug": s.moon_city, "default": s.moon_city_default},
        "day_off": {
            "days": _weekdays(a.day_off.days),
            "since": a.day_off.since.isoformat() if a.day_off.since else None,
            "before": _weekdays(a.day_off.before),
        },
        "hide_ladies": a.hide_ladies,
        "offer_check_in": a.offer_check_in,
        "created_at": _instant(a.created_at) if a.created_at else None,
        "last_seen_at": _instant(a.last_seen_at),
    }


def _settings(n: NotificationSettings) -> dict[str, object]:
    return {
        "moon": {"days_before": sorted(n.moon.offsets), "at": _time(n.moon.at)},
        "quiet_hours": {"start": _time(n.quiet.start), "end": _time(n.quiet.end)},
        "daily_cap": n.daily_cap,
        "practice": {
            "on": n.practice.on,
            "at": _time(n.practice.at),
            "days": sorted(n.practice.days),
        },
    }


def _practice(p: ExportPractice, labels: ExportLabels) -> dict[str, object]:
    pr, length = p.practice, p.practice.length
    end = length.end if length else None
    return {
        "date": p.local_date.isoformat(),
        "slot": pr.slot,
        "context": pr.context.value if pr.context else None,
        "online": pr.online,
        "series": list(length.series) if length else None,
        "end": end,
        "end_name": labels.stop(length.series[-1], end) if length and end else None,
        "first_part": length.first_part if length else None,
        "length": labels.length(length) if length else None,
        "duration_min": pr.duration_min,
        "start_time": _time(pr.start_time) if pr.start_time else None,
        "timezone": pr.timezone,
    }


def _check_in(c: CheckIn) -> dict[str, object]:
    return {
        "mood": c.mood,
        "energy": c.energy,
        "effort": c.effort,
        "tags": sorted(t.value for t in c.tags),
    }


def _progression(p: Progression | None, labels: ExportLabels) -> dict[str, object] | None:
    if p is None:
        return None
    return {
        "series": p.position.series,
        "last": p.position.key,
        "last_name": labels.position(p.position),
        "items": sorted(p.items),
    }


def _event(e: ExportEvent, labels: ExportLabels) -> dict[str, object]:
    ev = e.event
    return {
        "kind": ev.kind.value,
        "kind_label": _kind_label(ev, labels),
        "from": _position(ev.before),
        "from_name": labels.position(ev.before) if ev.before else None,
        "to": _position(ev.after),
        "to_name": labels.position(ev.after) if ev.after else None,
        "item": ev.item,
        "occurred_on": ev.occurred_on.isoformat(),
        "marked_by": e.marked_by.value,
        "created_at": _instant(e.created_at),
    }


def _position(p: Position | None) -> dict[str, str | None] | None:
    return None if p is None else {"series": p.series, "key": p.key}


def _day_code(d: ExportDay) -> str:
    """An unreadable seal is rest, never 🌸 (a guarantee here, not only in the adapter)."""
    return "rest" if d.unreadable else status_code(d.status)


def _day_label(d: ExportDay, labels: ExportLabels) -> str:
    return labels.unreadable_rest if d.unreadable else labels.status(status_code(d.status))


def _period_label(p: ExportPeriod, labels: ExportLabels) -> str:
    return labels.status(status_code(p.kind)) if p.kind else labels.unreadable_rest


def _kind_label(ev: ProgressionEvent, labels: ExportLabels) -> str:
    return labels.kind(ev.kind, labels.item(ev.item) if ev.item else "")


# --- CSV tables ---------------------------------------------------------------------------

DAYS_HEADER = [
    "date",
    "status",
    "status_label",
    "unreadable",
    "context",
    "online",
    "length",
    "series",
    "end",
    "end_name",
    "first_part",
    "duration_min",
    "start_time",
    "timezone",
    "mood",
    "energy",
    "effort",
    "tags",
    "note",
]
PERIODS_HEADER = ["start", "end", "kind", "kind_label", "unreadable"]
PROGRESSION_HEADER = [
    "occurred_on",
    "kind",
    "kind_label",
    "from",
    "from_name",
    "to",
    "to_name",
    "item",
    "marked_by",
    "created_at",
]


def to_tables(s: Snapshot, labels: ExportLabels) -> dict[str, list[list[str]]]:
    """Header row first; every cell a string (empty = none). One `days` row per date that has
    any record (a day, a practice, a check-in or a note)."""
    return {
        "days": [DAYS_HEADER, *_day_rows(s, labels)],
        "rest_periods": [
            PERIODS_HEADER,
            *(
                [
                    p.start.isoformat(),
                    p.end.isoformat(),
                    status_code(p.kind) if p.kind else "",
                    _period_label(p, labels),
                    _yes(p.unreadable),
                ]
                for p in s.periods
            ),
        ],
        "progression": [
            PROGRESSION_HEADER,
            *(
                [
                    e.event.occurred_on.isoformat(),
                    e.event.kind.value,
                    _kind_label(e.event, labels),
                    _cell_position(e.event.before),
                    labels.position(e.event.before) if e.event.before else "",
                    _cell_position(e.event.after),
                    labels.position(e.event.after) if e.event.after else "",
                    e.event.item or "",
                    e.marked_by.value,
                    _instant(e.created_at),
                ]
                for e in s.events
            ),
        ],
    }


def _day_rows(s: Snapshot, labels: ExportLabels) -> list[list[str]]:
    days = {d.local_date: d for d in s.days}
    practices = {p.local_date: p.practice for p in s.practices if p.practice.slot == 1}
    check_ins = {c.local_date: c.check_in for c in s.check_ins if c.check_in.slot == 1}
    notes = {n.local_date: n for n in s.notes}
    rows: list[list[str]] = []
    for day in sorted(days.keys() | practices.keys() | check_ins.keys() | notes.keys()):
        d, p, c, n = days.get(day), practices.get(day), check_ins.get(day), notes.get(day)
        length = p.length if p else None
        end = length.end if length else None
        rows.append(
            [
                day.isoformat(),
                _day_code(d) if d else "",
                _day_label(d, labels) if d else "",
                _yes((d is not None and d.unreadable) or (n is not None and n.unreadable)),
                p.context.value if p and p.context else "",
                ("yes" if p.online else "no") if p else "",
                labels.length(length) if length else "",
                " + ".join(length.series) if length else "",
                end or "",
                labels.stop(length.series[-1], end) if length and end else "",
                (length.first_part or "") if length else "",
                _num(p.duration_min if p else None),
                _time(p.start_time) if p and p.start_time else "",
                (p.timezone or "") if p else "",
                _num(c.mood if c else None),
                _num(c.energy if c else None),
                _num(c.effort if c else None),
                ", ".join(sorted(t.value for t in c.tags)) if c else "",
                (n.text or "") if n else "",
            ]
        )
    return rows


def _cell_position(p: Position | None) -> str:
    if p is None:
        return ""
    return f"{p.series}/{p.key}" if p.key else "standing"  # sun salutations and standing only


def _yes(flag: bool) -> str:
    return "yes" if flag else ""


def _num(value: int | None) -> str:
    return "" if value is None else str(value)


# --- formats ------------------------------------------------------------------------------


def _instant(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _time(at: time) -> str:
    return at.strftime("%H:%M")


def _weekdays(days: Weekdays | None) -> list[int] | None:
    return None if days is None else sorted(days)
