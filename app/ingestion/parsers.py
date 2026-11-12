"""CSV / JSONL parsing with row-level provenance."""
from __future__ import annotations

import csv
import json
from pathlib import Path

FAMILY_BY_MARKER = {
    "result": "login",
    "file_id": "file_access",
    "device_id": "usb",
    "image_name": "process",
    "print_job_id": "print",
    "message_id": "email_metadata",
}


def infer_family(filename: str, header: list[str] | None = None) -> str | None:
    name = Path(filename).name.lower()
    for fam in ("login", "file_access", "usb", "process", "print", "email_metadata"):
        if fam.replace("_", "") in name.replace("_", ""):
            return fam
    if header:
        for marker, fam in FAMILY_BY_MARKER.items():
            if marker in header:
                return fam
    return None


def parse_file(path: str | Path) -> list[dict]:
    """Return rows as dicts with '_source_record_id' attached (1-based row/line)."""
    path = Path(path)
    rows: list[dict] = []
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=1):
                row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
                row["_source_record_id"] = str(i)
                rows.append(row)
    elif path.suffix.lower() in (".jsonl", ".json"):
        with open(path, encoding="utf-8") as fh:
            if path.suffix.lower() == ".json":
                data = json.load(fh)
                items = data if isinstance(data, list) else [data]
                for i, item in enumerate(items, start=1):
                    item["_source_record_id"] = str(i)
                    rows.append(item)
            else:
                for i, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        rows.append({"_source_record_id": str(i), "_parse_error": "invalid JSONL line"})
                        continue
                    item["_source_record_id"] = str(i)
                    rows.append(item)
    else:
        raise ValueError(f"Unsupported file extension: {path.suffix}")
    return rows