"""The ST-09 ZIP (ADR-0027): exactly data.json, the three CSVs and README.txt; CSVs are UTF-8
with a BOM (spreadsheets), RFC 4180 quoting keeps line breaks and commas; JSON keeps Cyrillic
and emoji as they are."""

import csv
import io
import json
import zipfile

from tristhana.infrastructure.export_zip import ZipExportPacker

TABLES = {
    "days": [["date", "note"], ["2026-10-20", 'Лёгкая, "практика"\nвторая строка 🧘']],  # noqa: RUF001
    "rest_periods": [["start", "end"]],
    "progression": [["occurred_on", "kind"]],
}


async def _zip() -> zipfile.ZipFile:
    content = await ZipExportPacker().pack(
        {"schema": "tristhana.export/1", "note": "Майсур 🌙"}, TABLES, "Твои данные\n"
    )
    return zipfile.ZipFile(io.BytesIO(content))


async def test_exactly_the_five_files() -> None:
    z = await _zip()

    assert sorted(z.namelist()) == [
        "README.txt",
        "data.json",
        "days.csv",
        "progression.csv",
        "rest_periods.csv",
    ]
    assert z.testzip() is None


async def test_csvs_start_with_a_bom_and_round_trip() -> None:
    z = await _zip()
    raw = z.read("days.csv")

    assert raw.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    assert rows == TABLES["days"]


async def test_json_and_readme_keep_unicode() -> None:
    z = await _zip()

    assert json.loads(z.read("data.json")) == {"schema": "tristhana.export/1", "note": "Майсур 🌙"}
    assert "Майсур 🌙".encode() in z.read("data.json")
    assert z.read("README.txt").decode() == "Твои данные\n"
