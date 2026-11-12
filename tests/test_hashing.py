from app.ingestion.hashing import canonical_record_hash, sha256_bytes


def test_record_hash_deterministic_and_order_independent():
    a = {"event_id": "E1", "timestamp": "2026-11-02T09:00:00Z", "employee_id": "EMP-001"}
    b = {"employee_id": "EMP-001", "timestamp": "2026-11-02T09:00:00Z", "event_id": "E1"}
    assert canonical_record_hash(a) == canonical_record_hash(b)
    assert len(canonical_record_hash(a)) == 64


def test_bytes_hash():
    assert sha256_bytes(b"xai") != sha256_bytes(b"xai2")