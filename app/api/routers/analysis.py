from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.db.models import ModelRun
from app.detection.pipeline import queue_analysis

router = APIRouter()


class AnalysisRequest(BaseModel):
    dataset_id: str


@router.post("/analysis-runs", status_code=202)
def start_run(body: AnalysisRequest, db: Session = Depends(get_db),
              user=Depends(require_roles("admin", "analyst"))):
    run = queue_analysis(db, body.dataset_id)
    return {"run_id": run.id, "status": "queued"}


@router.get("/analysis-runs")
def list_runs(db: Session = Depends(get_db), user=Depends(require_roles("admin", "analyst", "reviewer"))):
    runs = db.query(ModelRun).order_by(ModelRun.started_at.desc().nullslast()).limit(20).all()
    return {"runs": [{"run_id": r.id, "dataset_id": r.dataset_id, "status": r.status,
                      "metrics": r.metrics, "error": r.error,
                      "started_at": r.started_at, "completed_at": r.completed_at} for r in runs]}


@router.get("/analysis-runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db),
            user=Depends(require_roles("admin", "analyst", "reviewer"))):
    run = db.get(ModelRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return {"run_id": run.id, "dataset_id": run.dataset_id, "status": run.status,
            "metrics": run.metrics, "error": run.error,
            "threshold_config": run.threshold_config,
            "started_at": run.started_at, "completed_at": run.completed_at}