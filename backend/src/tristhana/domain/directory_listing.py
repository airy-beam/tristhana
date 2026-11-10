"""The directory listing (ID-05, ADR-0042): one checked, dated fact about a teacher, "this name
is in the public teachers directory of Sharath Yoga Centre". A person looks it up by hand; the
server never calls that site. Not a level and not an endorsement: the level is the teacher's
own words. "Badge" is GM-02's word and is never used for this.

A teacher without the line is complete: nothing here produces a negative mark, and no rule
sorts, counts or compares teachers by it. No rule reads practice data.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

DIRECTORY_URL = "https://sharathyogacentre.com/authorised-teachers-directory/"
NAME_MAX = 100
REGION_MAX = 60
NOTE_MAX = 300
RESEND_AFTER = timedelta(hours=24)  # an account causes at most one admin note a day
_BIDI_CONTROLS = re.compile("[‪-‮⁦-⁩‎‏]")
_WHITESPACE = re.compile(r"\s+")


class ListingStatus(StrEnum):
    PENDING = "pending"
    LISTED = "listed"
    NOT_FOUND = "not_found"
    WITHDRAWN = "withdrawn"


class DeclaredLevel(StrEnum):
    """The teacher's own words. Plain "Authorised" predates the levels."""

    AUTHORISED = "authorised"
    AUTHORISED_1 = "authorised-1"
    AUTHORISED_2 = "authorised-2"
    CERTIFIED = "certified"


class Outcome(StrEnum):
    LISTED = "listed"
    NOT_FOUND = "not_found"


class Step(StrEnum):
    SEND = "send"  # a new request: admins get one note
    EDIT = "edit"  # a waiting request changed in place: no note
    LEVEL_ONLY = "level_only"  # the level is self-declared: stays listed, no check
    RECHECK = "recheck"  # a listed name or region changed: the line hides until checked


class InvalidListing(Exception):
    """A field is empty, too long or unknown. Carries no value."""


class ListingWait(Exception):
    """Sent again too soon. `wait`: until the next send is possible."""

    def __init__(self, wait: timedelta) -> None:
        super().__init__()
        self.wait = wait


@dataclass(frozen=True, slots=True)
class Listing:
    status: ListingStatus
    name_as_listed: str | None  # None only when withdrawn
    region: str | None
    level: DeclaredLevel | None
    note: str | None  # for the checker only; kept only while pending
    revision: int
    requested_at: datetime  # the last send
    checked_on: date | None


@dataclass(frozen=True, slots=True)
class ListingMark:
    """All that crosses accounts, and only for a listed row."""

    name_as_listed: str
    checked_on: date
    level: DeclaredLevel | None


@dataclass(frozen=True, slots=True)
class Details:
    name_as_listed: str
    region: str
    level: DeclaredLevel | None
    note: str | None


def _text(raw: str | None) -> str:
    text = _BIDI_CONTROLS.sub("", raw or "")
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return _WHITESPACE.sub(" ", text).strip()


def clean(name: str | None, region: str | None, level: str | None, note: str | None) -> Details:
    """Printable and single-spaced. Too long is refused, never cut: the name is shown to
    students exactly as sent. Raises `InvalidListing`."""
    name_, region_, note_ = _text(name), _text(region), _text(note)
    if not name_ or len(name_) > NAME_MAX or not region_ or len(region_) > REGION_MAX:
        raise InvalidListing
    if len(note_) > NOTE_MAX:
        raise InvalidListing
    try:
        level_ = DeclaredLevel(level) if level else None
    except ValueError:
        raise InvalidListing from None
    return Details(name_, region_, level_, note_ or None)


def wait_left(current: Listing | None, now: datetime) -> timedelta | None:
    """How long until this account may cause another admin note; None: it may now."""
    if current is None:
        return None
    left = current.requested_at + RESEND_AFTER - now
    return left if left > timedelta(0) else None


def next_state(current: Listing | None, details: Details, now: datetime) -> Step:
    """What saving `details` does. Raises `ListingWait` when it would send admins a second
    note within a day (a new request, or a listed name changed)."""
    if current is not None and current.status is ListingStatus.PENDING:
        return Step.EDIT
    if current is not None and current.status is ListingStatus.LISTED:
        same = (current.name_as_listed, current.region) == (details.name_as_listed, details.region)
        if same:
            return Step.LEVEL_ONLY
        step = Step.RECHECK
    else:
        step = Step.SEND
    left = wait_left(current, now)
    if left is not None:
        raise ListingWait(left)
    return step


def mark_of(listing: Listing | None) -> ListingMark | None:
    if listing is None or listing.status is not ListingStatus.LISTED:
        return None
    if listing.name_as_listed is None or listing.checked_on is None:
        return None
    return ListingMark(listing.name_as_listed, listing.checked_on, listing.level)


def may_decide(listing: Listing) -> bool:
    """A waiting request gets its answer; a listed one can be re-checked. Either outcome."""
    return listing.status in (ListingStatus.PENDING, ListingStatus.LISTED)
