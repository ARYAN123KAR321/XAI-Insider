"""Run (or re-run) the detection pipeline and print evaluation metrics.

Usage: python scripts/evaluate.py [dataset_id]
Without dataset_id the most recent dataset is used.
"""
from __future__ import annotations

import json
import sys

from app.db.database import SessionLocal
from app.db.models import Dataset, ModelRun
from app.detection.pipeline import run_analysis_sync


def main():
    db = SessionLocal()
    if len(sys.argv) > 1:
        dataset_id = sys.argv[1]
    else:
        ds = db.query(Dataset).order_by(Dataset.created_at.desc()).first()
        if ds is None:
            print("No dataset found. Run scripts/generate_data.py + ingest first.")
            return
        dataset_id = ds.id
    db.close()

    print(f"Running analysis on dataset {dataset_id} ...")
    run_id = run_analysis_sync(dataset_id)

    db = SessionLocal()
    run = db.get(ModelRun, run_id)
    print(json.dumps(run.metrics, indent=2, default=str))
    db.close()


if __name__ == "__main__":
    main()