"""Reports & exports: history + independent hash verification (plan §10.4, T-10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.cases.zip_export import verify_package
from app.db.models import Case, CaseExport
from app.ingestion.hashing import sha256_file

router = APIRouter()


@router.get("/reports/exports")
def list_exports(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(CaseExport).order_by(CaseExport.created_at.desc())).scalars().all()
    out = []
    for e in rows:
        case = db.get(Case, e.case_id)
        out.append({
            "export_id": e.id, "case_id": e.case_id,
            "case_title": case.title if case else "-",
            "status": e.status, "zip_sha256": e.zip_sha256,
            "created_at": e.created_at,
        })
    return {"exports": out}


@router.get("/reports/exports/{export_id}/verify")
def verify_export(export_id: str, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    export = db.get(CaseExport, export_id)
    if export is None:
        raise HTTPException(404, "export not found")
    if export.status != "verified" or not export.zip_path:
        raise HTTPException(409, f"export not available (status={export.status})")

    current_sha = sha256_file(export.zip_path)
    zip_ok = current_sha == export.zip_sha256
    pkg = verify_package(export.zip_path, export.manifest or {})
    return {
        "export_id": export_id,
        "zip_sha256_stored": export.zip_sha256,
        "zip_sha256_recomputed": current_sha,
        "zip_integrity": "verified" if zip_ok else "mismatch",
        "manifest_check": pkg["integrity_status"],
        "files_checked": pkg["files_checked"],
        "mismatches": pkg["mismatches"],
    }