from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import ModelRun, ModelVersion, ScoredWindow

router = APIRouter()


@router.get("/models")
def list_models(db: Session = Depends(get_db), user=Depends(get_current_user)):
    versions = db.query(ModelVersion).order_by(ModelVersion.trained_at.desc()).all()
    return {"models": [{
        "model_version_id": m.id, "algorithm": m.algorithm, "parameters": m.parameters,
        "feature_schema_version": m.feature_schema_version,
        "artifact_sha256": m.artifact_sha256, "trained_at": m.trained_at,
        "training_dataset_id": m.training_dataset_id,
    } for m in versions]}


@router.get("/models/runs/{run_id}/score-distribution")
def score_distribution(run_id: str, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    run = db.get(ModelRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    rows = db.execute(select(ScoredWindow.normalized_score, ScoredWindow.is_alert)
                      .where(ScoredWindow.run_id == run_id)).all()
    scores = [float(r[0]) for r in rows]
    return {
        "run_id": run_id,
        "n_windows": len(scores),
        "histogram": _histogram(scores, bins=20),
        "alerts": int(sum(1 for r in rows if r[1])),
        "metrics": run.metrics,
    }


def _histogram(values: list[float], bins: int) -> list[dict]:
    if not values:
        return []
    lo, hi = 0.0, 100.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[max(idx, 0)] += 1
    return [{"bin_start": round(lo + i * width, 1), "bin_end": round(lo + (i + 1) * width, 1),
             "count": counts[i]} for i in range(bins)]


@router.get("/health")
def health():
    return {"status": "ok", "service": "xai-insider-api", "version": "1.0.0"}