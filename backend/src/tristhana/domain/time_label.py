"""When a displayed time carries its UTC offset (ADR-0044). The place always shows
(`07:00 Almaty`); the offset is added only for a zone that is not the viewer's own
(`17:30 Berlin (UTC+1)`). The city name is the formatter's business, not this module's.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

UTC_NAME = "UTC"


def offset_shown(zone: str, viewer_zone: str | None) -> bool:
    """False in the viewer's own zone: the same IANA name, not an equal clock, so the answer
    never flips on a daylight-saving date. An unknown viewer zone shows the offset (nothing
    is "your own" yet). `UTC` never gets one: `07:00 UTC` already says it."""
    return zone != UTC_NAME and zone != viewer_zone


def offset_text(zone: str, day: date, at: time) -> str:
    """`UTC+5`, `UTC+5:30`, `UTC-3:30`: the zone's offset at that wall-clock time on that
    date, so daylight saving is right."""
    offset = datetime.combine(day, at, ZoneInfo(zone)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    hours = f"{minutes // 60}" + (f":{minutes % 60:02d}" if minutes % 60 else "")
    return f"UTC{sign}{hours}"
