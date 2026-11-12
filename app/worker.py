"""Background worker: executes queued ingestion jobs, analysis runs, and exports.

Run standalone:  python -m app.worker
(The API embeds this loop for single-process local demos.)
"""
from __future__ import annotations

import time

from sqlalchemy import select

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.db.models import Case, CaseExport, IngestionJob, ModelRun


def process_one() -> bool:
    """Claim and execute at most one queued unit of work. Returns True if work was done."""
    db = SessionLocal()
    try:
        job = db.execute(select(IngestionJob).where(IngestionJob.status == "queued")
                         .order_by(IngestionJob.id)).scalars().first()
        if job:
            job_id = job.id
            db.close()
            from app.ingestion.pipeline import run_ingestion_job
            run_ingestion_job(job_id)
            return True

        run = db.execute(select(ModelRun).where(ModelRun.status == "queued")
                         .order_by(ModelRun.id)).scalars().first()
        if run:
            run_id, dataset_id = run.id, run.dataset_id
            db.close()
            from app.detection.pipeline import run_analysis_sync
            try:
                run_analysis_sync(dataset_id, run_id=run_id)
            except Exception as exc:  # noqa: BLE001
                print(f"analysis run failed: {exc}")
            return True

        export = db.execute(select(CaseExport).where(CaseExport.status == "queued")
                            .order_by(CaseExport.id)).scalars().first()
        if export:
            export_id, case_id = export.id, export.case_id
            db.close()
            _run_export_job(export_id, case_id)
            return True
        return False
    finally:
        db.close()


def _run_export_job(export_id: str, case_id: str) -> None:
    from app.cases.evidence import collect_evidence
    from app.cases.pdf_report import build_case_pdf
    from app.cases.workflow import log_audit
    from app.cases.zip_export import build_evidence_zip
    from app.ingestion.hashing import sha256_file

    db = SessionLocal()
    try:
        export = db.get(CaseExport, export_id)
        export.status = "generating"
        db.commit()
        case = db.get(Case, case_id)
        try:
            collect_evidence(db, case, actor_id=None)
            pdf_path, _ = build_case_pdf(db, case)
            zip_path, manifest, ok = build_evidence_zip(db, case, pdf_path)
            export.pdf_path = str(pdf_path)
            export.zip_path = str(zip_path)
            export.zip_sha256 = sha256_file(zip_path)
            export.manifest = manifest
            export.status = "verified" if ok else "failed"
            log_audit(db, None, "case.export", "case", case_id,
                      {"export_id": export_id, "verified": ok})
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            export = db.get(CaseExport, export_id)
            export.status = "failed"
            export.error = str(exc)
        db.commit()
    finally:
        db.close()


def main():
    settings = get_settings()
    settings.ensure_dirs()
    print("XAI-Insider worker started.")
    while True:
        try:
            if not process_one():
                time.sleep(settings.worker_poll_seconds)
        except Exception as exc:  # noqa: BLE001
            print(f"worker error: {exc}")
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()