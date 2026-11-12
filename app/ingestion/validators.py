"""Row-level schema validation and UTC normalization (plan §6.2–6.3)."""
from __future__ import annotations

from datetime import datetime, timezone

COMMON_REQUIRED = ["event_id", "timestamp", "employee_id", "host_id"]

FAMILY_REQUIRED = {
    "login": ["result", "auth_method"],
    "file_access": ["file_id", "action", "bytes"],
    "usb": ["device_id", "action"],
    "process": ["process_guid", "image_name"],
    "print": ["print_job_id", "pages"],
    "email_metadata": ["message_id", "recipient_count"],
}

ENUMS = {
    "login": {"result": {"success", "failure"}},
    "file_access": {"action": {"read", "write", "delete", "rename"}},
    "usb": {"action": {"mount", "read", "write", "eject"}},
}

NUMERIC_FIELDS = {
    "file_access": ["bytes"],
    "usb": ["bytes_transferred"],
    "print": ["pages"],
    "email_metadata": ["recipient_count", "external_recipient_count",
                       "attachment_count", "attachment_bytes"],
}


def parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_rows(family: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split rows into (valid, rejected). Rejected rows carry row-level reasons."""
    valid, rejected = [], []
    required = COMMON_REQUIRED + FAMILY_REQUIRED.get(family, [])

    for row in rows:
        src = row.get("_source_record_id", "?")
        if row.get("_parse_error"):
            rejected.append({"row": src, "field": None, "message": row["_parse_error"]})
            continue

        problem = None
        for field in required:
            if row.get(field) in (None, ""):
                problem = {"row": src, "field": field, "message": f"missing required field '{field}'"}
                break
        if problem:
            rejected.append(problem)
            continue

        try:
            ts = parse_timestamp(row["timestamp"])
        except (ValueError, TypeError):
            rejected.append({"row": src, "field": "timestamp",
                             "message": f"invalid timestamp: {row.get('timestamp')!r}"})
            continue

        enum_problems = ENUMS.get(family, {})
        bad_enum = None
        for field, allowed in enum_problems.items():
            if str(row.get(field)).lower() not in allowed:
                bad_enum = {"row": src, "field": field,
                            "message": f"value {row.get(field)!r} not in {sorted(allowed)}"}
                break
        if bad_enum:
            rejected.append(bad_enum)
            continue

        num_problem = None
        parsed_numbers = {}
        for field in NUMERIC_FIELDS.get(family, []):
            raw = row.get(field, 0) or 0
            try:
                val = float(raw)
                if val < 0:
                    raise ValueError("negative value")
                parsed_numbers[field] = int(val) if float(val).is_integer() else val
            except (TypeError, ValueError):
                num_problem = {"row": src, "field": field, "message": f"invalid numeric value: {raw!r}"}
                break
        if num_problem:
            rejected.append(num_problem)
            continue

        norm = {k: v for k, v in row.items() if not k.startswith("_")}
        norm["timestamp"] = ts
        norm["_source_record_id"] = src
        norm.update({f"_{k}_num": v for k, v in parsed_numbers.items()})
        valid.append(norm)

    return valid, rejected