"""When a displayed time carries its UTC offset (ADR-0044). The place always shows
(`07:00 Almaty`); the offset is added only for a zone that is not the viewer's own
(`17:30 Berlin (UTC+1)`). The city name is the formatter's business, not this module's.
"""

from datetime import date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

UTC_NAME = "UTC"

# One zone, two names. Chrome and Android's WebView still report CLDR's ids (the left
# column); the seeded cities and Firefox use IANA's own (the right). `zoneinfo` reads both
# and never says they are one zone, so the rule below asks this table. The Mini App's
# `timeLabel.ts` holds the same table, and both test files pin it.
ZONE_ALIASES: Final[dict[str, str]] = {
    "Africa/Asmera": "Africa/Asmara",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Jujuy": "America/Argentina/Jujuy",
    "America/Mendoza": "America/Argentina/Mendoza",
    "America/Coral_Harbour": "America/Atikokan",
    "America/Godthab": "America/Nuuk",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Louisville": "America/Kentucky/Louisville",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "Europe/Kiev": "Europe/Kyiv",
    "Pacific/Enderbury": "Pacific/Kanton",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Truk": "Pacific/Chuuk",
}


def canonical_zone(zone: str) -> str:
    """IANA's own name for a zone that also goes by an older one (`Asia/Calcutta`)."""
    return ZONE_ALIASES.get(zone, zone)


def offset_shown(zone: str, viewer_zone: str | None) -> bool:
    """False in the viewer's own zone: the same IANA zone (under either of its names), not
    an equal clock, so the answer never flips on a daylight-saving date. An unknown viewer
    zone shows the offset (nothing is "your own" yet). `UTC` never gets one: `07:00 UTC`
    already says it."""
    if zone == UTC_NAME:
        return False
    return viewer_zone is None or canonical_zone(zone) != canonical_zone(viewer_zone)


def offset_text(zone: str, day: date, at: time) -> str:
    """`UTC+5`, `UTC+5:30`, `UTC-3:30`: the zone's offset at that wall-clock time on that
    date, so daylight saving is right."""
    offset = datetime.combine(day, at, ZoneInfo(zone)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    hours = f"{minutes // 60}" + (f":{minutes % 60:02d}" if minutes % 60 else "")
    return f"UTC{sign}{hours}"
