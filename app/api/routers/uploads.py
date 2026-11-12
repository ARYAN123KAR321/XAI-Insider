from __future__ import annotations

import csv
import io
import shutil
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.config.settings import get_settings
from app.db.models import Alert, Dataset, Event, IngestionJob, Upload
from app.ingestion.hashing import sha256_file
from app.ingestion.pipeline import create_dataset
from app.simulator.generator import GenConfig, Generator, write_dataset
from app.util.ids import new_id, utcnow

router = APIRouter()

ALLOWED_SUFFIXES = {".csv", ".jsonl", ".json"}


class GenerateRequest(BaseModel):
    seed: int = 42
    days: int = 7


class UploadResponse(BaseModel):
    upload_id: str
    dataset_id: str
    job_id: str
    source_sha256: str
    status: str


def _neutralize(value) -> str:
    """Neutralize spreadsheet formula injection in CSV exports (§13.2)."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@router.post("/simulator/generate")
def generate_dataset(body: GenerateRequest,
                     user=Depends(require_roles("admin", "analyst"))):
    settings = get_settings()
    result = Generator(GenConfig(seed=body.seed, days=body.days)).run()
    out_dir = settings.generated_dir / result["manifest"]["dataset_name"]
    paths = write_dataset(out_dir, result)
    return {
        "dataset_name": result["manifest"]["dataset_name"],
        "directory": str(out_dir),
        "files": {k: str(p) for k, p in paths.items()},
        "scenarios": [s["scenario_id"] for s in result["manifest"]["scenarios"]],
        "hint": "Upload these files via POST /api/v1/uploads (family per file, plus 'manifest').",
    }


@router.post("/uploads", response_model=UploadResponse, status_code=202)
async def upload_file(file: UploadFile = File(...),
                      family: str = Form("auto"),
                      dataset_id: str | None = Form(None),
                      dataset_name: str | None = Form(None),
                      db: Session = Depends(get_db),
                      user=Depends(require_roles("admin", "analyst"))):
    settings = get_settings()
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(422, f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}")

    tmp_dir = settings.upload_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{new_id('raw')}{suffix}"
    size = 0
    with open(tmp_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"Upload exceeds {settings.max_upload_mb} MB limit")
            out.write(chunk)

    if dataset_id:
        ds = db.get(Dataset, dataset_id)
        if ds is None:
            raise HTTPException(404, "dataset not found")
    else:
        ds = create_dataset(db, name=dataset_name or f"dataset-{utcnow():%Y%m%d-%H%M%S}")

    digest = sha256_file(tmp_path)
    final_dir = settings.upload_dir / ds.id
    final_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name.replace("/", "_").replace("..", "_")
    final_path = final_dir / f"{digest[:12]}_{safe_name}"
    shutil.move(str(tmp_path), final_path)

    effective_family = "manifest" if (suffix == ".json" and
                                      "manifest" in safe_name.lower()) else family
    upload = Upload(id=new_id("upl"), dataset_id=ds.id, original_name=safe_name,
                    stored_path=str(final_path), family=effective_family, sha256=digest,
                    size_bytes=size, uploaded_by=user.id)
    db.add(upload)
    db.flush()
    job = IngestionJob(id=new_id("job"), upload_id=upload.id, status="queued")
    db.add(job)
    db.commit()

    return UploadResponse(upload_id=upload.id, dataset_id=ds.id, job_id=job.id,
                          source_sha256=digest, status="queued")


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"job_id": job.id, "status": job.status, "accepted": job.accepted_count,
            "rejected": job.rejected_count, "duplicates": job.duplicate_count,
            "errors": (job.error_summary or [])[:20],
            "started_at": job.started_at, "completed_at": job.completed_at}


@router.get("/jobs/{job_id}/validation-report")
def validation_report(job_id: str, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    """Downloadable validation CSV (§6.4) with formula-neutralized cells."""
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["row", "field", "message"])
    for err in (job.error_summary or []):
        writer.writerow([_neutralize(err.get("row")), _neutralize(err.get("field")),
                         _neutralize(err.get("message"))])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="validation_report_{job_id}.csv"'})


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), user=Depends(get_current_user)):
    out = []
    for ds in db.query(Dataset).order_by(Dataset.created_at.desc()).all():
        counts = dict(db.execute(select(Event.event_type, func.count(Event.id))
                                 .where(Event.dataset_id == ds.id)
                                 .group_by(Event.event_type)).all())
        out.append({"dataset_id": ds.id, "name": ds.name, "created_at": ds.created_at,
                    "total_events": sum(counts.values()), "family_counts": counts,
                    "has_labels": bool(ds.label_manifest and ds.label_manifest.get("scenarios")),
                    "scenario_count": len((ds.label_manifest or {}).get("scenarios", []))})
    return {"datasets": out}


@router.get("/datasets/{dataset_id}/quality")
def dataset_quality(dataset_id: str, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "dataset not found")
    counts = dict(db.execute(select(Event.event_type, func.count(Event.id))
                             .where(Event.dataset_id == dataset_id)
                             .group_by(Event.event_type)).all())
    span = db.execute(select(func.min(Event.timestamp_utc), func.max(Event.timestamp_utc))
                      .where(Event.dataset_id == dataset_id)).one()
    n_emp = db.execute(select(func.count(func.distinct(Event.employee_id)))
                       .where(Event.dataset_id == dataset_id)).scalar()
    n_host = db.execute(select(func.count(func.distinct(Event.host_id)))
                        .where(Event.dataset_id == dataset_id)).scalar()
    expected = {"login", "file_access", "usb", "process", "print", "email_metadata"}
    missing = sorted(expected - set(counts))
    return {
        "dataset_id": dataset_id, "total_events": sum(counts.values()),
        "family_counts": counts, "time_range": {"start": span[0], "end": span[1]},
        "employees": n_emp, "hosts": n_host, "missing_families": missing,
        "warning": (f"Missing telemetry families: {', '.join(missing)}. "
                    "Interpretation may be affected.") if missing else None,
        "has_label_manifest": bool(ds.label_manifest),
    }


@router.get("/datasets/{dataset_id}/activity-summary")
def activity_summary(dataset_id: str, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    """Hour×weekday heatmap, family counts, and alert distribution (§11.2)."""
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "dataset not found")

    rows = db.execute(select(Event.timestamp_utc, Event.event_type)
                      .where(Event.dataset_id == dataset_id)).all()
    heatmap = [[0] * 24 for _ in range(7)]
    by_family: dict[str, int] = {}
    for ts, fam in rows:
        t = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        heatmap[t.weekday()][t.hour] += 1
        by_family[fam] = by_family.get(fam, 0) + 1

    alerts = db.execute(select(Alert).where(Alert.dataset_id == dataset_id)).scalars().all()
    by_band = {"high": 0, "medium": 0, "low": 0}
    by_date: dict[str, int] = {}
    for a in alerts:
        by_band[a.priority_band] = by_band.get(a.priority_band, 0) + 1
        d = a.window_start.astimezone(timezone.utc).strftime("%Y-%m-%d") \
            if a.window_start.tzinfo else a.window_start.strftime("%Y-%m-%d")
        by_date[d] = by_date.get(d, 0) + 1

    return {"heatmap": heatmap, "by_family": by_family,
            "alerts_by_band": by_band, "alerts_by_date": by_date}