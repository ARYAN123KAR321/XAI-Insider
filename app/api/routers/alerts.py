from __future__ import annotations

import joblib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.cases.workflow import log_audit
from app.db.models import (Alert, Counterfactual, Event, Explanation, FeatureWindow,
                           ModelRun, ModelVersion)
from app.explainability.counterfactual import run_counterfactual

router = APIRouter()

ALLOWED_TRANSITIONS = {
    "new": {"in_review"},
    "in_review": {"case_linked", "closed_benign", "closed_suspicious", "closed_inconclusive"},
    "case_linked": {"closed_benign", "closed_suspicious", "closed_inconclusive"},
}


class StatusBody(BaseModel):
    status: str


@router.get("/alerts")
def list_alerts(dataset_id: str | None = None, priority_band: str | None = None,
                employee_id: str | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = select(Alert)
    if dataset_id:
        q = q.where(Alert.dataset_id == dataset_id)
    if priority_band:
        q = q.where(Alert.priority_band == priority_band)
    if employee_id:
        q = q.where(Alert.employee_id == employee_id)

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    alerts = db.execute(q.order_by(Alert.priority_score.desc())
                        .offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "alerts": [{
            "alert_id": a.id, "employee_id": a.employee_id, "dataset_id": a.dataset_id,
            "window_start": a.window_start, "window_end": a.window_end,
            "normalized_score": round(a.normalized_score, 1),
            "priority_score": round(a.priority_score, 1), "priority_band": a.priority_band,
            "status": a.status, "run_id": a.run_id,
        } for a in alerts],
        "page": page, "page_size": page_size, "total": int(total),
    }


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    expl = db.execute(select(Explanation).where(Explanation.alert_id == alert_id)).scalars().first()
    window = db.get(FeatureWindow, alert.window_id)

    evidence_events = []
    if expl and expl.evidence_event_ids:
        evs = db.execute(select(Event).where(Event.event_id.in_(expl.evidence_event_ids),
                                             Event.dataset_id == alert.dataset_id)).scalars().all()
        evidence_events = [{
            "event_id": e.event_id, "timestamp_utc": e.timestamp_utc, "event_type": e.event_type,
            "employee_id": e.employee_id, "host_id": e.host_id, "metadata": e.metadata_,
            "source_record_id": e.source_record_id, "raw_record_hash": e.raw_record_hash,
        } for e in sorted(evs, key=lambda x: x.timestamp_utc)]

    run = db.get(ModelRun, alert.run_id) if alert.run_id else None
    mv = db.get(ModelVersion, run.model_version_id) if run and run.model_version_id else None

    counterfactuals = db.execute(select(Counterfactual)
                                 .where(Counterfactual.alert_id == alert_id)
                                 .order_by(Counterfactual.created_at.desc())).scalars().all()

    return {
        "alert": {
            "alert_id": alert.id, "employee_id": alert.employee_id,
            "window_start": alert.window_start, "window_end": alert.window_end,
            "raw_score": alert.raw_score, "normalized_score": alert.normalized_score,
            "priority_score": alert.priority_score, "priority_band": alert.priority_band,
            "status": alert.status, "run_id": alert.run_id,
            "model_version_id": mv.id if mv else None,
        },
        "window_features": window.features if window else {},
        "explanation": ({
            "method": expl.method, "baseline_used": expl.baseline_used,
            "feature_reasons": expl.feature_reasons,
            "evidence_event_ids": expl.evidence_event_ids, "caveats": expl.caveats,
        } if expl else None),
        "evidence_events": evidence_events,
        "counterfactuals": [{
            "id": c.id, "original_score": c.original_score,
            "hypothetical_score": c.hypothetical_score, "changes": c.changes,
            "constraints": c.constraints, "created_at": c.created_at,
        } for c in counterfactuals],
    }


@router.patch("/alerts/{alert_id}/status")
def update_alert_status(alert_id: str, body: StatusBody, db: Session = Depends(get_db),
                        user=Depends(require_roles("admin", "analyst"))):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    allowed = ALLOWED_TRANSITIONS.get(alert.status, set())
    if body.status not in allowed:
        raise HTTPException(409, f"cannot transition from '{alert.status}' to '{body.status}'")
    log_audit(db, user.id, "alert.status", "alert", alert_id,
              {"from": alert.status, "to": body.status})
    alert.status = body.status
    db.commit()
    return {"alert_id": alert_id, "status": alert.status}


@router.post("/alerts/{alert_id}/counterfactuals")
def create_counterfactual(alert_id: str, db: Session = Depends(get_db),
                          user=Depends(require_roles("admin", "analyst"))):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    run = db.get(ModelRun, alert.run_id)
    mv = db.get(ModelVersion, run.model_version_id) if run else None
    if mv is None:
        raise HTTPException(409, "no model version associated with this alert")
    artifact = joblib.load(mv.artifact_path)
    window = db.get(FeatureWindow, alert.window_id)

    cf = run_counterfactual(artifact, window, alert, requested_by=user.id)
    db.add(cf)
    log_audit(db, user.id, "counterfactual.request", "alert", alert_id)
    db.commit()
    db.refresh(cf)
    return {"id": cf.id, "original_score": cf.original_score,
            "hypothetical_score": cf.hypothetical_score, "changes": cf.changes,
            "constraints": cf.constraints}


@router.get("/employees/{employee_id}/timeline")
def employee_timeline(employee_id: str, dataset_id: str,
                      start: str | None = None, end: str | None = None,
                      limit: int = Query(2000, le=5000),
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import datetime

    def _parse(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, f"Invalid timestamp format: {value!r}")

    start_dt, end_dt = _parse(start), _parse(end)
    q = select(Event).where(Event.dataset_id == dataset_id,
                            Event.employee_id == employee_id).order_by(Event.timestamp_utc)
    if start_dt:
        q = q.where(Event.timestamp_utc >= start_dt)
    if end_dt:
        q = q.where(Event.timestamp_utc < end_dt)
    evs = db.execute(q.limit(limit)).scalars().all()
    return {"employee_id": employee_id, "events": [{
        "event_id": e.event_id, "timestamp_utc": e.timestamp_utc, "event_type": e.event_type,
        "host_id": e.host_id, "session_id": e.session_id, "metadata": e.metadata_,
    } for e in evs]}