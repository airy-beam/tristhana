"""`ExportPacker`: the ST-09 ZIP (ADR-0027). Stdlib only; packing runs in a worker thread so a
big export doesn't stall other requests on the event loop."""

import asyncio
import csv
import io
import json
import zipfile

_BOM = "﻿"  # spreadsheets (Excel) read UTF-8 CSV correctly only with it


class ZipExportPacker:
    async def pack(
        self, data: dict[str, object], tables: dict[str, list[list[str]]], readme: str
    ) -> bytes:
        return await asyncio.to_thread(pack_zip, data, tables, readme)


def pack_zip(data: dict[str, object], tables: dict[str, list[list[str]]], readme: str) -> bytes:
    """data.json, `<table>.csv` (UTF-8 with BOM, RFC 4180, CRLF rows), README.txt."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        for name, rows in tables.items():
            text = io.StringIO()
            text.write(_BOM)
            csv.writer(text, lineterminator="\r\n").writerows(rows)
            z.writestr(f"{name}.csv", text.getvalue())
        z.writestr("README.txt", readme)
    return buffer.getvalue()
