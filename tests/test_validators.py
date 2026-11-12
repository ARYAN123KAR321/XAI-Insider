from datetime import datetime, timezone

from app.ingestion.validators import validate_rows


def _row(**over):
    base = {"event_id": "LOG-1", "timestamp": "2026-11-02T09:00:00Z",
            "employee_id": "EMP-001", "host_id": "HOST-01",
            "result": "success", "auth_method": "password", "_source_record_id": "1"}
    base.update(over)
    return base


def test_valid_login_row():
    valid, rejected = validate_rows("login", [_row()])
    assert len(valid) == 1 and not rejected
    assert valid[0]["timestamp"].tzinfo == timezone.utc


def test_invalid_timestamp_rejected_with_reason():
    valid, rejected = validate_rows("login", [_row(timestamp="not-a-time")])
    assert not valid and len(rejected) == 1
    assert rejected[0]["field"] == "timestamp"


def test_missing_required_field_rejected():
    row = _row()
    del row["employee_id"]
    valid, rejected = validate_rows("login", [row])
    assert not valid and rejected[0]["field"] == "employee_id"


def test_bad_enum_rejected():
    valid, rejected = validate_rows("login", [_row(result="maybe")])
    assert not valid and rejected[0]["field"] == "result"