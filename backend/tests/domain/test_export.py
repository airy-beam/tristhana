"""Export (ST-09, ADR-0027): the snapshot as versioned JSON and CSV tables. Pure.

Owner rules: the owner's own export carries true values (🌸 included); an unreadable seal
says rest and never guesses 🌸; `skipped` is `no_practice` in the export vocabulary; only
stored facts (no derived day off / moon / pause days); no internal guards, no names."""

import csv
import io
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from tristhana.domain.accounts import Account
from tristhana.domain.check_in import CheckIn, CheckInTag
from tristhana.domain.days import DayStatus
from tristhana.domain.export import (
    EXPORT_EVERY,
    SCHEMA,
    ExportCheckIn,
    ExportDay,
    ExportEvent,
    ExportIdentity,
    ExportLabels,
    ExportMilestone,
    ExportNote,
    ExportPeriod,
    ExportPractice,
    ExportReminder,
    MarkedBy,
    Snapshot,
    check_rate,
    export_file_name,
    to_json,
    to_tables,
)
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import Practice, PracticeContext, PracticeLength
from tristhana.domain.progression import EventKind, Position, Progression, ProgressionEvent
from tristhana.domain.rest_days import DayOff

NOW = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
ID = UUID("6f1c2d4e-0000-4000-8000-000000000001")
D1, D2, D3 = date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)


def _labels(prefix: str = "") -> ExportLabels:
    """Readable fakes: every label says where it came from (a RU fake uses Cyrillic)."""
    return ExportLabels(
        status=lambda code: f"{prefix}status:{code}",
        position=lambda p: f"{prefix}pos:{p.series}/{p.key}" if p.key else f"{prefix}standing",
        stop=lambda series, key: f"{prefix}stop:{key}",
        item=lambda key: f"{prefix}item:{key}",
        kind=lambda kind, item: f"{prefix}kind:{kind.value}:{item}",
        length=lambda length: f"{prefix}len:{'+'.join(length.series) or 'short'}",
        unreadable_rest=f"{prefix}unreadable-rest",
    )


def _account(**kw: object) -> Account:
    base: dict[str, object] = dict(
        id=ID,
        display_name="Asha",
        locale="en",
        timezone="Asia/Almaty",
        last_seen_at=NOW,
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        day_off=DayOff(frozenset({6}), D1, frozenset({7})),
        day_off_dismissed=True,
    )
    base.update(kw)
    return Account(**base)  # type: ignore[arg-type]


def _snapshot(**kw: object) -> Snapshot:
    base: dict[str, object] = dict(
        account=_account(),
        identities=(ExportIdentity("telegram", "1234567", NOW - timedelta(days=300)),),
        settings=DEFAULTS,
        moon_city="mysuru",
        moon_city_default=True,
        catalog_version="cat-1",
        days=(),
        periods=(),
        practices=(),
        check_ins=(),
        notes=(),
        progression=None,
        events=(),
        reminders=(),
        exported_at=NOW,
    )
    base.update(kw)
    return Snapshot(**base)  # type: ignore[arg-type]


def _rows(tables: dict[str, list[list[str]]], name: str) -> list[dict[str, str]]:
    header, *rows = tables[name]
    return [dict(zip(header, row, strict=True)) for row in rows]


# --- JSON ---------------------------------------------------------------------------------


def test_schema_is_versioned() -> None:
    out = to_json(_snapshot(), _labels())

    assert SCHEMA == "tristhana.export/1"
    assert out["schema"] == SCHEMA
    assert out["exported_at"] == "2026-10-27T09:30:00Z"
    assert out["catalog_version"] == "cat-1"


def test_json_is_serializable() -> None:
    snap = _snapshot(
        days=(ExportDay(D1, DayStatus.PRACTICED, "Asia/Almaty"),),
        practices=(
            ExportPractice(
                D1,
                Practice(
                    PracticeContext.MYSORE,
                    length=PracticeLength(("primary",), "navasana"),
                    duration_min=90,
                    start_time=time(6, 30),
                    timezone="Asia/Almaty",
                ),
            ),
        ),
    )

    json.dumps(to_json(snap, _labels()), ensure_ascii=False)


def test_practice_milestones_keep_their_order_and_utc_instants() -> None:
    later = datetime(2027, 3, 1, 4, 0, tzinfo=UTC)
    milestones = (ExportMilestone(100, NOW, False), ExportMilestone(365, later, True))

    out = to_json(_snapshot(milestones=milestones), _labels())

    assert out["schema"] == "tristhana.export/1"  # additive: no bump
    assert out["practice_milestones"] == [
        {"count": 100, "reached_at": "2026-10-27T09:30:00Z", "celebrated": False},
        {"count": 365, "reached_at": "2027-03-01T04:00:00Z", "celebrated": True},
    ]
    assert to_json(_snapshot(), _labels())["practice_milestones"] == []


def test_account_keys_are_exactly_the_public_ones() -> None:
    account = to_json(_snapshot(), _labels())["account"]

    assert set(account) == {
        "id",
        "display_name",
        "name_from_telegram",
        "locale",
        "locale_from_telegram",
        "timezone",
        "moon_city",
        "day_off",
        "hide_ladies",
        "offer_check_in",
        "created_at",
        "last_seen_at",
    }
    assert account["moon_city"] == {"slug": "mysuru", "default": True}


def test_day_off_is_iso_weekdays_with_its_history() -> None:
    day_off = to_json(_snapshot(), _labels())["account"]["day_off"]

    assert day_off == {"days": [6], "since": "2026-10-20", "before": [7]}


def test_day_off_never_chosen_is_null_days() -> None:
    snap = _snapshot(account=_account(day_off=DayOff()))

    assert to_json(snap, _labels())["account"]["day_off"] == {
        "days": None,
        "since": None,
        "before": None,
    }


def test_no_internal_guards_anywhere() -> None:
    snap = _snapshot(
        progression=Progression(
            Position("primary", "navasana"),
            frozenset({"drop-backs"}),
            last_event_id=41,
            hint=Position("primary", "kukkutasana"),
            hint_event_id=41,
        )
    )
    text = json.dumps(to_json(snap, _labels()))

    for guard in (
        "last_event_id",
        "hint",
        "day_off_dismissed",
        "moon_intro_sent_at",
        "unreachable_at",
        "export_claimed_at",
        "dedupe",
        "attempts",
    ):
        assert guard not in text


def test_skipped_exports_as_no_practice_and_never_skipped() -> None:
    snap = _snapshot(days=(ExportDay(D1, DayStatus.SKIPPED, "Asia/Almaty"),))

    out = to_json(snap, _labels())
    tables = to_tables(snap, _labels())

    assert out["days"][0]["status"] == "no_practice"
    assert out["days"][0]["status_label"] == "status:no_practice"
    assert "skipped" not in json.dumps(out)
    assert "skipped" not in repr(tables)


def test_ladies_day_and_period_keep_their_true_value() -> None:
    snap = _snapshot(
        days=(ExportDay(D1, DayStatus.LADIES, "Asia/Almaty"),),
        periods=(ExportPeriod(D2, D3, DayStatus.LADIES),),
    )

    out = to_json(snap, _labels())

    assert out["days"][0] == {
        "date": "2026-10-20",
        "status": "ladies",
        "status_label": "status:ladies",
        "timezone": "Asia/Almaty",
        "unreadable": False,
    }
    assert out["rest_periods"][0] == {
        "start": "2026-10-21",
        "end": "2026-10-22",
        "kind": "ladies",
        "kind_label": "status:ladies",
        "unreadable": False,
    }


def test_unreadable_day_says_rest_never_ladies() -> None:
    snap = _snapshot(days=(ExportDay(D1, DayStatus.LADIES, None, unreadable=True),))

    day = to_json(snap, _labels())["days"][0]

    assert day["status"] == "rest"
    assert day["unreadable"] is True
    assert day["status_label"] == "unreadable-rest"
    assert "ladies" not in json.dumps(day)


def test_unreadable_period_has_null_kind() -> None:
    snap = _snapshot(periods=(ExportPeriod(D1, D3, None),))

    period = to_json(snap, _labels())["rest_periods"][0]

    assert period["kind"] is None
    assert period["unreadable"] is True
    assert period["kind_label"] == "unreadable-rest"


def test_unreadable_note_has_null_text() -> None:
    snap = _snapshot(notes=(ExportNote(D1, None), ExportNote(D2, "Felt light")))

    assert to_json(snap, _labels())["diary"] == [
        {"date": "2026-10-20", "text": None, "unreadable": True},
        {"date": "2026-10-21", "text": "Felt light", "unreadable": False},
    ]


def test_practice_fields_with_labels_and_the_zone_of_its_own_time() -> None:
    practice = Practice(
        PracticeContext.MYSORE,
        online=False,
        length=PracticeLength(("primary", "intermediate"), "pincha-mayurasana", "second_half"),
        duration_min=90,
        start_time=time(6, 30),
        timezone="Asia/Kolkata",
    )
    snap = _snapshot(practices=(ExportPractice(D1, practice),))

    assert to_json(snap, _labels())["practices"] == [
        {
            "date": "2026-10-20",
            "slot": 1,
            "context": "mysore",
            "online": False,
            "series": ["primary", "intermediate"],
            "end": "pincha-mayurasana",
            "end_name": "stop:pincha-mayurasana",
            "first_part": "second_half",
            "length": "len:primary+intermediate",
            "duration_min": 90,
            "start_time": "06:30",
            "timezone": "Asia/Kolkata",
        }
    ]


def test_practice_without_length_has_null_series() -> None:
    snap = _snapshot(practices=(ExportPractice(D1, Practice()),))

    practice = to_json(snap, _labels())["practices"][0]

    assert practice["series"] is None
    assert practice["length"] is None
    assert practice["end_name"] is None


def test_check_in_tags_sorted() -> None:
    check_in = CheckIn(4, 3, None, frozenset({CheckInTag.STRONG, CheckInTag.CALM}))
    snap = _snapshot(check_ins=(ExportCheckIn(D1, check_in),))

    assert to_json(snap, _labels())["check_ins"] == [
        {
            "date": "2026-10-20",
            "slot": 1,
            "mood": 4,
            "energy": 3,
            "effort": None,
            "tags": ["calm", "strong"],
        }
    ]


def test_no_progression_is_null() -> None:
    assert to_json(_snapshot(), _labels())["progression"] is None


def test_progression_position_and_items() -> None:
    snap = _snapshot(
        progression=Progression(Position("primary", "navasana"), frozenset({"tic-tacs", "b"}))
    )

    assert to_json(snap, _labels())["progression"] == {
        "series": "primary",
        "last": "navasana",
        "last_name": "pos:primary/navasana",
        "items": ["b", "tic-tacs"],
    }


@pytest.mark.parametrize(
    ("marked_by", "code"),
    [(MarkedBy.SELF, "self"), (MarkedBy.TEACHER, "teacher"), (MarkedBy.UNKNOWN, "unknown")],
)
def test_events_carry_who_marked_them_without_an_id_or_name(marked_by: MarkedBy, code: str) -> None:
    teacher = uuid4()
    event = ProgressionEvent(
        7, EventKind.GIVEN, D1, Position("primary", "navasana"), Position("primary", "bhuja")
    )
    snap = _snapshot(events=(ExportEvent(event, marked_by, NOW),))

    (out,) = to_json(snap, _labels())["progression_events"]

    assert out == {
        "kind": "given",
        "kind_label": "kind:given:",
        "from": {"series": "primary", "key": "navasana"},
        "from_name": "pos:primary/navasana",
        "to": {"series": "primary", "key": "bhuja"},
        "to_name": "pos:primary/bhuja",
        "item": None,
        "occurred_on": "2026-10-20",
        "marked_by": code,
        "created_at": "2026-10-27T09:30:00Z",
    }
    assert str(teacher) not in json.dumps(out)
    assert "7" not in json.dumps(out["kind_label"])


def test_item_event_label_names_the_item() -> None:
    event = ProgressionEvent(3, EventKind.ITEM_GIVEN, D1, item="drop-backs")
    snap = _snapshot(events=(ExportEvent(event, MarkedBy.SELF, NOW),))

    (out,) = to_json(snap, _labels())["progression_events"]

    assert out["kind_label"] == "kind:item_given:item:drop-backs"
    assert out["from"] is None
    assert out["to"] is None


def test_standing_only_position_is_null_series_and_key() -> None:
    event = ProgressionEvent(1, EventKind.START, D1, None, Position())
    snap = _snapshot(events=(ExportEvent(event, MarkedBy.SELF, NOW),))

    (out,) = to_json(snap, _labels())["progression_events"]

    assert out["to"] == {"series": None, "key": None}
    assert out["to_name"] == "standing"


def test_reminders_and_identities() -> None:
    snap = _snapshot(reminders=(ExportReminder("moon", D1, "sent"),))

    out = to_json(snap, _labels())

    assert out["reminders"] == [{"category": "moon", "date": "2026-10-20", "status": "sent"}]
    assert out["identities"] == [
        {"provider": "telegram", "id": "1234567", "linked_at": "2025-12-31T09:30:00Z"}
    ]


def test_notification_settings_are_the_effective_values() -> None:
    out = to_json(_snapshot(), _labels())["notification_settings"]

    assert out == {
        "moon": {"days_before": [1, 7], "at": "19:00"},
        "quiet_hours": {"start": "22:00", "end": "07:00"},
        "daily_cap": 3,
        "practice": {"on": None, "at": "10:00", "days": [1, 2, 3, 4, 5, 7]},
    }


# --- CSV tables ---------------------------------------------------------------------------


def test_table_headers() -> None:
    tables = to_tables(_snapshot(), _labels())

    assert set(tables) == {"days", "rest_periods", "progression"}
    assert tables["days"][0] == [
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
    assert tables["rest_periods"][0] == ["start", "end", "kind", "kind_label", "unreadable"]
    assert tables["progression"][0] == [
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


def test_one_row_per_date_in_date_order() -> None:
    snap = _snapshot(
        days=(
            ExportDay(D2, DayStatus.PRACTICED, "Asia/Almaty"),
            ExportDay(D1, DayStatus.MOON, "Asia/Almaty"),
        ),
        practices=(ExportPractice(D2, Practice(PracticeContext.SELF, length=PracticeLength())),),
        check_ins=(ExportCheckIn(D2, CheckIn(5, tags=frozenset({CheckInTag.LIGHT}))),),
        notes=(ExportNote(D2, "two records, one row"), ExportNote(D3, "note only")),
    )

    rows = _rows(to_tables(snap, _labels()), "days")

    assert [r["date"] for r in rows] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    moon, practiced, note_only = rows
    assert moon["status"] == "moon"
    assert moon["context"] == ""
    assert moon["note"] == ""
    assert practiced["status"] == "practiced"
    assert practiced["context"] == "self"
    assert practiced["online"] == "no"
    assert practiced["length"] == "len:short"
    assert practiced["series"] == ""
    assert practiced["mood"] == "5"
    assert practiced["energy"] == ""
    assert practiced["tags"] == "light"
    assert practiced["note"] == "two records, one row"
    assert note_only["status"] == ""
    assert note_only["status_label"] == ""
    assert note_only["note"] == "note only"


def test_practice_without_check_in_leaves_the_check_in_columns_empty() -> None:
    snap = _snapshot(
        days=(ExportDay(D1, DayStatus.PRACTICED, None),),
        practices=(
            ExportPractice(
                D1,
                Practice(
                    PracticeContext.LED,
                    online=True,
                    length=PracticeLength(("primary", "intermediate"), "kapotasana", "first_half"),
                ),
            ),
        ),
    )

    (row,) = _rows(to_tables(snap, _labels()), "days")

    assert row["online"] == "yes"
    assert row["series"] == "primary + intermediate"
    assert row["end"] == "kapotasana"
    assert row["end_name"] == "stop:kapotasana"
    assert row["first_part"] == "first_half"
    assert (row["mood"], row["energy"], row["effort"], row["tags"]) == ("", "", "", "")


def test_unreadable_row_says_rest_and_yes() -> None:
    snap = _snapshot(
        days=(ExportDay(D1, DayStatus.REST, None, unreadable=True),),
        notes=(ExportNote(D2, None),),
    )

    rest, note = _rows(to_tables(snap, _labels()), "days")

    assert (rest["status"], rest["status_label"], rest["unreadable"]) == (
        "rest",
        "unreadable-rest",
        "yes",
    )
    assert note["unreadable"] == "yes"
    assert note["note"] == ""


def test_rest_periods_end_inclusive_and_labels() -> None:
    snap = _snapshot(
        periods=(ExportPeriod(D1, D3, DayStatus.SICK), ExportPeriod(D2, D3, None)),
    )

    assert _rows(to_tables(snap, _labels()), "rest_periods") == [
        {
            "start": "2026-10-20",
            "end": "2026-10-22",
            "kind": "sick",
            "kind_label": "status:sick",
            "unreadable": "",
        },
        {
            "start": "2026-10-21",
            "end": "2026-10-22",
            "kind": "",
            "kind_label": "unreadable-rest",
            "unreadable": "yes",
        },
    ]


def test_progression_rows() -> None:
    events = (
        ExportEvent(
            ProgressionEvent(1, EventKind.START, D1, None, Position("primary", "navasana")),
            MarkedBy.SELF,
            NOW,
        ),
        ExportEvent(
            ProgressionEvent(2, EventKind.ITEM_REMOVED, D2, item="tic-tacs"),
            MarkedBy.UNKNOWN,
            NOW,
        ),
    )

    start, removed = _rows(to_tables(_snapshot(events=events), _labels()), "progression")

    assert start == {
        "occurred_on": "2026-10-20",
        "kind": "start",
        "kind_label": "kind:start:",
        "from": "",
        "from_name": "",
        "to": "primary/navasana",
        "to_name": "pos:primary/navasana",
        "item": "",
        "marked_by": "self",
        "created_at": "2026-10-27T09:30:00Z",
    }
    assert removed["item"] == "tic-tacs"
    assert removed["kind_label"] == "kind:item_removed:item:tic-tacs"
    assert removed["marked_by"] == "unknown"


def test_labels_come_from_the_labels_passed_in() -> None:
    snap = _snapshot(
        days=(ExportDay(D1, DayStatus.PRACTICED, None),),
        practices=(ExportPractice(D1, Practice(length=PracticeLength(("primary",), "navasana"))),),
    )

    (row,) = _rows(to_tables(snap, _labels("ru:")), "days")

    assert row["status_label"] == "ru:status:practiced"
    assert row["end_name"] == "ru:stop:navasana"


def test_multiline_cyrillic_note_round_trips_through_csv() -> None:
    text = 'Лёгкая практика.\nУчитель сказал: "дыши".\r\n, точка'  # noqa: RUF001
    snap = _snapshot(notes=(ExportNote(D1, text),))
    buffer = io.StringIO()
    csv.writer(buffer).writerows(to_tables(snap, _labels())["days"])

    rows = list(csv.DictReader(io.StringIO(buffer.getvalue(), newline="")))

    assert rows[0]["note"] == text


# --- rate limit and file name -------------------------------------------------------------


def test_export_every_ten_minutes() -> None:
    assert timedelta(minutes=10) == EXPORT_EVERY


def test_check_rate() -> None:
    assert check_rate(None, NOW) is None
    assert check_rate(NOW - timedelta(minutes=9, seconds=59), NOW) == timedelta(seconds=1)
    assert check_rate(NOW - timedelta(minutes=10), NOW) is None
    assert check_rate(NOW - timedelta(hours=3), NOW) is None


def test_check_rate_clock_moved_back_waits_at_most_the_window() -> None:
    assert check_rate(NOW + timedelta(minutes=5), NOW) == EXPORT_EVERY


def test_file_name_is_the_local_date() -> None:
    assert export_file_name(date(2026, 10, 28)) == "tristhana-export-2026-10-28.zip"
