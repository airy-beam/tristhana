"""A shala's Classes list (UI-06 stage 6, spec §3.1): which series are current and how their
weekdays read. The cases are shared with the Mini App (screens/shalas/classList.test.ts), so the
bot's list and the app's cannot drift: data/classes/class_list_cases.json."""

import json
from datetime import date, time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from tristhana.domain.classes import ClassSeries, ClassType, current_classes, day_runs

CASES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[3] / "data" / "classes" / "class_list_cases.json").read_text()
)


def _id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, name)


def _series(row: dict[str, Any]) -> ClassSeries:
    return ClassSeries(
        id=_id(row["id"]),
        type=ClassType(row["type"]),
        title=None,
        online=False,
        zone="Asia/Almaty",
        teacher_id=None,
        start=time.fromisoformat(row["start"]),
        minutes=90,
        weekdays=frozenset(row["weekdays"]),
        every=1,
        starts_on=date.fromisoformat(row["starts_on"]),
        ends_on=date.fromisoformat(row["ends_on"]) if row["ends_on"] else None,
    )


@pytest.mark.parametrize("case", CASES["day_runs"], ids=lambda c: c["name"])
def test_day_runs(case: dict[str, Any]) -> None:
    assert day_runs(case["weekdays"]) == tuple(tuple(run) for run in case["runs"])


@pytest.mark.parametrize("case", CASES["current_classes"], ids=lambda c: c["name"])
def test_current_classes(case: dict[str, Any]) -> None:
    rows = case["classes"]
    # The ids sort by their UUIDs here and by their names in the app: no case may hinge on it.
    names = {_id(row["id"]): row["id"] for row in rows}

    kept = current_classes([_series(row) for row in rows], date.fromisoformat(case["today"]))

    assert [names[c.id] for c in kept] == case["expected"]


def test_the_shared_table_is_read() -> None:
    assert len(CASES["day_runs"]) >= 5
    assert len(CASES["current_classes"]) >= 5
