from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.cases.evidence import collect_evidence
from app.cases.workflow import (add_note, create_case, link_alert, log_audit,
                                set_disposition, set_status)
from app.db.models import Alert, Case, CaseExport, CaseNote, EvidenceItem
from app.util.ids import new_id

router = APIRouter()


class CaseCreate(BaseModel):
    title: str
    priority: str = "medium"


class LinkAlertBody(BaseModel):
    alert_id: str


class NoteBody(BaseModel):
    text: str


class DispositionBody(BaseModel):
    disposition: str
    rationale: str | None = None


class EvidenceBody(BaseModel):
    alert_ids: list[str] | None = None


class ReviewBody(BaseModel):
    action: str          # start_review | complete_review
    comment: str | None = None


@router.post("/cases", status_code=201)
def api_create_case(body: CaseCreate, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "analyst"))):
    case = create_case(db, body.title, user.id, body.priority)
    return {"case_id": case.id, "status": case.status}


@router.get("/cases")
def list_cases(db: Session = Depends(get_db), user=Depends(get_current_user)):
    cases = db.query(Case).order_by(Case.updated_at.desc()).all()
    return {"cases": [{"case_id": c.id, "title": c.title, "status": c.status,
                       "disposition": c.disposition, "priority": c.priority,
                       "alert_count": len(c.alert_ids or []),
                       "created_at": c.created_at, "updated_at": c.updated_at} for c in cases]}


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    notes = db.execute(select(CaseNote).where(CaseNote.case_id == case_id)
                       .order_by(CaseNote.created_at)).scalars().all()
    items = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case_id)).scalars().all()
    exports = db.execute(select(CaseExport).where(CaseExport.case_id == case_id)
                         .order_by(CaseExport.created_at.desc())).scalars().all()
    return {
        "case": {"case_id": case.id, "title": case.title, "status": case.status,
                 "disposition": case.disposition, "rationale": case.disposition_rationale,
                 "priority": case.priority, "alert_ids": case.alert_ids,
                 "created_at": case.created_at, "closed_at": case.closed_at},
        "notes": [{"id": n.id, "text": n.note_text, "created_at": n.created_at} for n in notes],
        "evidence": [{"id": i.id, "item_type": i.item_type, "source_reference": i.source_reference,
                      "sha256": i.sha256, "size_bytes": i.size_bytes,
                      "integrity_status": i.integrity_status,
                      "collected_at": i.collected_at} for i in items],
        "exports": [{"export_id": e.id, "status": e.status, "zip_sha256": e.zip_sha256,
                     "created_at": e.created_at} for e in exports],
    }


@router.post("/cases/{case_id}/alerts")
def api_link_alert(case_id: str, body: LinkAlertBody, db: Session = Depends(get_db),
                   user=Depends(require_roles("admin", "analyst"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    alert = db.get(Alert, body.alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    link_alert(db, case, body.alert_id, user.id)
    if alert.status in ("new", "in_review"):
        alert.status = "case_linked"
        db.commit()
    return {"case_id": case.id, "alert_ids": case.alert_ids}


@router.post("/cases/{case_id}/notes")
def api_add_note(case_id: str, body: NoteBody, db: Session = Depends(get_db),
                user=Depends(require_roles("admin", "analyst", "reviewer"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    note = add_note(db, case, body.text, user.id)
    return {"note_id": note.id, "created_at": note.created_at}


@router.post("/cases/{case_id}/review")
def api_review_case(case_id: str, body: ReviewBody, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "reviewer"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    if body.action == "start_review":
        set_status(db, case, "under_review", user.id)
    elif body.action == "complete_review":
        set_status(db, case, "pending_approval", user.id)
        if body.comment:
            add_note(db, case, f"[REVIEW] {body.comment}", user.id)
    else:
        raise HTTPException(422, "action must be start_review or complete_review")
    return {"case_id": case.id, "status": case.status}


@router.post("/cases/{case_id}/disposition")
def api_disposition(case_id: str, body: DispositionBody, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "analyst"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    allowed = {"benign", "suspicious", "inconclusive", "needs_follow_up"}
    if body.disposition not in allowed:
        raise HTTPException(422, f"disposition must be one of {sorted(allowed)}")
    set_disposition(db, case, body.disposition, body.rationale, user.id)
    return {"case_id": case.id, "status": case.status, "disposition": case.disposition}


@router.post("/cases/{case_id}/evidence")
def api_collect_evidence(case_id: str, body: EvidenceBody, db: Session = Depends(get_db),
                         user=Depends(require_roles("admin", "analyst"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    if body.alert_ids:
        for aid in body.alert_ids:
            link_alert(db, case, aid, user.id)
    added = collect_evidence(db, case, user.id)
    return {"case_id": case.id, "items_added": added}


@router.post("/cases/{case_id}/exports", status_code=202)
def api_create_export(case_id: str, db: Session = Depends(get_db),
                      user=Depends(require_roles("admin", "analyst"))):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    export = CaseExport(id=new_id("exp"), case_id=case_id, status="queued")
    db.add(export)
    log_audit(db, user.id, "case.export_requested", "case", case_id)
    db.commit()
    return {"export_id": export.id, "status": "queued"}


@router.get("/exports/{export_id}")
def get_export(export_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    export = db.get(CaseExport, export_id)
    if export is None:
        raise HTTPException(404, "export not found")
    return {"export_id": export.id, "case_id": export.case_id, "status": export.status,
            "zip_sha256": export.zip_sha256, "error": export.error,
            "manifest": export.manifest,
            "downloads": {"pdf": f"/downloads/{export.id}/pdf",
                          "zip": f"/downloads/{export.id}/zip"}
            if export.status == "verified" else None}


@router.get("/downloads/{export_id}/{kind}")
def download_export(export_id: str, kind: str, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    export = db.get(CaseExport, export_id)
    if export is None or export.status != "verified":
        raise HTTPException(404, "export not available")
    if kind == "pdf" and export.pdf_path:
        return FileResponse(export.pdf_path, media_type="application/pdf",
                            filename=f"case_{export.case_id}_report.pdf")
    if kind == "zip" and export.zip_path:
        return FileResponse(export.zip_path, media_type="application/zip",
                            filename=f"case_{export.case_id}_evidence.zip")
    raise HTTPException(404, "artifact not found")