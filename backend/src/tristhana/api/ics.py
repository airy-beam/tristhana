"""The ICS serializer (SC-06, ADR-0036): RFC 5545 text for a `Feed`, hand-written and pure.

CRLF line ends; lines folded at 75 octets without splitting a UTF-8 character; TEXT values
escaped (backslash, comma, semicolon, newline) and stripped of control characters (names and
titles are user text). Instants in UTC (`…Z`), all-day events as `VALUE=DATE`. No VTIMEZONE,
RRULE, SEQUENCE or VALARM. `DTSTAMP` is the link's creation, so the same content gives the
same bytes (and ETag) on every poll.
"""

import re
from datetime import UTC, date, datetime

from tristhana.application.calendar_feed import Feed
from tristhana.domain.calendar_feed import FeedEvent

_LIMIT = 75  # octets per physical line, CRLF excluded
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # all but TAB and LF (CR is handled first)
_HEADER = (
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Tristhana//SC-06//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
)
_REFRESH = ("REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H")


def _text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "")
    value = _CONTROL.sub("", value)
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Greedy: the first line takes up to 75 octets, each continuation a space and up to 74."""
    if len(line) <= _LIMIT // 4 or len(line.encode()) <= _LIMIT:  # most lines: no fold
        return [line]
    out: list[str] = []
    current, size, limit = "", 0, _LIMIT
    for ch in line:
        width = len(ch.encode())
        if size + width > limit:
            out.append(current)
            current, size, limit = " ", 1, _LIMIT
        current += ch
        size += width
    out.append(current)
    return out


def _instant(at: datetime) -> str:
    return f"{at.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _when(name: str, value: datetime | date, all_day: bool) -> str:
    if all_day or not isinstance(value, datetime):
        return f"{name};VALUE=DATE:{value:%Y%m%d}"
    return f"{name}:{_instant(value)}"


def _event(e: FeedEvent, stamp: str) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{e.uid}",
        f"DTSTAMP:{stamp}",
        _when("DTSTART", e.start, e.all_day),
        _when("DTEND", e.end, e.all_day),
    ]
    if e.all_day:
        lines.append("TRANSP:TRANSPARENT")  # a moon day doesn't block time
    for name, value in (("SUMMARY", e.summary), ("DESCRIPTION", e.description)):
        if value:
            lines.append(f"{name}:{_text(value)}")
    if e.location:
        lines.append(f"LOCATION:{_text(e.location)}")
    lines.append("END:VEVENT")
    return lines


def render(feed: Feed) -> bytes:
    stamp = _instant(feed.stamp)
    logical = [*_HEADER, f"X-WR-CALNAME:{_text(feed.name)}", *_REFRESH]
    for e in feed.events:
        logical += _event(e, stamp)
    logical.append("END:VCALENDAR")
    physical = [part for line in logical for part in _fold(line)]
    return ("\r\n".join(physical) + "\r\n").encode()
