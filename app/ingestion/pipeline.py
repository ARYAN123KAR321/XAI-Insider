"""Ingestion orchestration: parse -> validate -> normalize -> dedupe -> persist."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.db.models import Dataset, Event, IngestionJob, Upload
from app.ingestion.hashing import canonical_record_hash, sha256_file
from app.ingestion.parsers import infer_family, parse_file
from app.ingestion.validators import COMMON_REQUIRED, validate_rows
from app.util.ids import new_id, utcnow

BATCH_SIZE = 500


def create_dataset(db, name: str, seed: int | None = None) -> Dataset:
    ds = Dataset(id=new_id("ds"), name=name, generator_seed=seed)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def _normalize_event(family: str, row: dict, dataset_id: str, upload_id: str) -> dict:
    ts = row["timestamp"]
    metadata = {k: v for k, v in row.items()
                if k not in COMMON_REQUIRED + ["session_id", "process_guid", "parent_guid"]
                and not k.startswith("_")}
    for k, v in list(row.items()):
        if k.startswith("_") and k.endswith("_num"):
            metadata[k[1:-4]] = v
    return {
        "id": new_id("ev"),
        "event_id": row["event_id"],
        "dataset_id": dataset_id,
        "employee_id": row["employee_id"],
        "host_id": row["host_id"],
        "event_type": family,
        "timestamp_utc": ts,
        "session_id": row.get("session_id") or None,
        "process_guid": row.get("process_guid") or None,
        "parent_process_guid": row.get("parent_guid") or None,
        "metadata_": metadata,
        "source_file_id": upload_id,
        "source_record_id": str(row["_source_record_id"]),
        "raw_record_hash": canonical_record_hash(
            {k: v for k, v in row.items() if not k.startswith("_") and k != "timestamp"}
            | {"timestamp": ts.isoformat()}),
        "ingested_at_utc": utcnow(),
    }


def _apply_manifest(db, upload: Upload, path: Path) -> dict:
    with open(path) as fh:
        manifest = json.load(fh)
    ds = db.get(Dataset, upload.dataset_id)
    ds.label_manifest = {
        "splits": manifest.get("splits", {}),
        "scenarios": manifest.get("scenarios", []),
        "date_range": manifest.get("date_range", {}),
    }
    ds.employee_meta = {e["employee_id"]: e for e in manifest.get("employees", [])}
    db.commit()
    return {"accepted": 1, "rejected": 0, "duplicates": 0, "errors": []}


def ingest_file_sync(db, upload: Upload) -> dict:
    """Synchronous ingestion of one upload. Returns counters."""
    settings = get_settings()
    path = Path(upload.stored_path)

    if upload.family == "manifest":
        return _apply_manifest(db, upload, path)

    rows = parse_file(path)
    header = list(rows[0].keys()) if rows else []
    family = upload.family if upload.family != "auto" else infer_family(path.name, header)
    if family is None:
        return {"accepted": 0, "rejected": len(rows), "duplicates": 0,
                "errors": [{"row": None, "field": None, "message": "could not infer event family"}]}

    valid, rejected = validate_rows(family, rows)

    # dedupe against existing events in this dataset
    incoming_ids = [r["event_id"] for r in valid]
    existing = set()
    for i in range(0, len(incoming_ids), BATCH_SIZE):
        chunk = incoming_ids[i:i + BATCH_SIZE]
        res = db.execute(select(Event.event_id).where(
            Event.dataset_id == upload.dataset_id, Event.event_id.in_(chunk)))
        existing.update(res.scalars().all())

    accepted, duplicates, errors = 0, 0, [dict(e) for e in rejected]
    seen_in_file = set()
    batch = []
    for row in valid:
        eid = row["event_id"]
        if eid in existing or eid in seen_in_file:
            duplicates += 1
            continue
        seen_in_file.add(eid)
        batch.append(Event(**_normalize_event(family, row, upload.dataset_id, upload.id)))
        accepted += 1
        if len(batch) >= BATCH_SIZE:
            db.bulk_save_objects(batch)
            db.commit()
            batch = []
    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    upload.family = family
    db.commit()
    return {"accepted": accepted, "rejected": len(rejected), "duplicates": duplicates,
            "errors": errors[:50], "family": family}


def run_ingestion_job(job_id: str) -> None:
    """Worker entrypoint."""
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if job is None or job.status != "queued":
            return
        job.status = "running"
        job.started_at = utcnow()
        db.commit()

        upload = db.get(Upload, job.upload_id)
        try:
            report = ingest_file_sync(db, upload)
            job.accepted_count = report["accepted"]
            job.rejected_count = report["rejected"]
            job.duplicate_count = report["duplicates"]
            job.error_summary = report.get("errors") or None
            job.family_counts = {report.get("family", upload.family): report["accepted"]}
            job.status = "completed_with_errors" if report["rejected"] else "completed"
        except Exception as exc:  # noqa: BLE001 - report and continue
            db.rollback()
            job = db.get(IngestionJob, job_id)
            job.status = "failed"
            job.error_summary = [{"row": None, "field": None, "message": str(exc)}]
        job.completed_at = utcnow()
        db.commit()
    finally:
        db.close()