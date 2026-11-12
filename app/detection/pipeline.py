"""End-to-end analysis run: features -> baselines -> models -> alerts -> explanations.

Implements plan §7-§9:
- Isolation Forest (required primary model, §8.1)
- Robust z-score baseline (required sanity baseline, §8.4)
- Optional autoencoder comparison (FR-19)
- MLflow experiment tracking when available (FR-18)
Scenario labels are used ONLY for evaluation, never for training (§8.5).
"""
from __future__ import annotations

from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.db.models import (Alert, Dataset, Event, Explanation, FeatureWindow,
                           ModelRun, ModelVersion, ScoredWindow)
from app.detection import autoencoder, baseline_zscore, tracking
from app.detection.evaluation import evaluate
from app.detection.model import raw_scores, train_isolation_forest
from app.detection.preprocessing import fit_preprocessor, transform
from app.detection.scoring import normalize_scores, priority_band, priority_score
from app.explainability.explanations import explain_window
from app.features.baselines import compute_baselines
from app.features.registry import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.features.windows import build_windows
from app.ingestion.hashing import sha256_file
from app.util.ids import new_id, utcnow


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _load_events(db, dataset_id: str) -> list[dict]:
    rows = db.execute(select(Event).where(Event.dataset_id == dataset_id)).scalars().all()
    return [{"id": r.id, "event_id": r.event_id, "employee_id": r.employee_id,
             "host_id": r.host_id, "event_type": r.event_type, "ts": r.timestamp_utc,
             "session_id": r.session_id, "metadata": r.metadata_} for r in rows]


def _known_sets(db, dataset_id: str, train_start, train_end) -> tuple[dict, dict]:
    rows = db.execute(select(Event).where(
        Event.dataset_id == dataset_id,
        Event.timestamp_utc >= train_start, Event.timestamp_utc < train_end)).scalars().all()
    devices, procs = {}, {}
    for r in rows:
        if r.event_type == "usb" and r.metadata_.get("device_id"):
            devices.setdefault(r.employee_id, set()).add(r.metadata_["device_id"])
        if r.event_type == "process" and r.metadata_.get("image_name"):
            procs.setdefault(r.employee_id, set()).add(r.metadata_["image_name"])
    return devices, procs


def run_analysis_sync(dataset_id: str, run_id: str | None = None) -> str:
    """Run the full analysis. Uses an existing queued run row when run_id is given."""
    settings = get_settings()
    db = SessionLocal()
    if run_id:
        run = db.get(ModelRun, run_id)
        run.status, run.started_at = "running", utcnow()
    else:
        run = ModelRun(id=new_id("run"), dataset_id=dataset_id,
                       status="running", started_at=utcnow())
        db.add(run)
    db.commit()

    try:
        ds = db.get(Dataset, dataset_id)
        events = _load_events(db, dataset_id)
        if not events:
            raise RuntimeError("dataset has no ingested events")

        # ---- temporal splits -------------------------------------------------
        manifest = ds.label_manifest or {}
        splits = manifest.get("splits")
        if splits:
            train_start = _parse_iso(splits["train"]["start"])
            train_end = _parse_iso(splits["train"]["end"])
            calib_start = _parse_iso(splits["calibration"]["start"])
            calib_end = _parse_iso(splits["calibration"]["end"])
            test_start = _parse_iso(splits["test"]["start"])
            test_end = _parse_iso(splits["test"]["end"])
        else:
            ts = sorted(e["ts"] for e in events)
            span = (ts[-1] - ts[0]).total_seconds()
            train_start = ts[0]
            train_end = ts[0] + pd.Timedelta(seconds=span * 0.7)
            calib_start = train_end
            calib_end = train_end + pd.Timedelta(seconds=span * 0.15)
            test_start = calib_end
            test_end = ts[-1] + pd.Timedelta(seconds=1)

        employee_meta = ds.employee_meta or {}
        known_devices, known_procs = _known_sets(db, dataset_id, train_start, train_end)

        # ---- windows & feature matrix ----------------------------------------
        windows = build_windows(events, employee_meta, known_devices, known_procs,
                                settings.window_minutes, settings.stride_minutes)
        X_all = np.array([[w.features[n] for n in FEATURE_NAMES] for w in windows], dtype=float)
        wdf = pd.DataFrame(X_all, columns=FEATURE_NAMES)
        wdf["employee_id"] = [w.employee_id for w in windows]
        wdf["start"] = [w.start for w in windows]
        wdf["role"] = [(employee_meta.get(w.employee_id) or {}).get("role") for w in windows]

        train_mask = (wdf["start"] >= train_start) & (wdf["start"] < train_end)
        calib_mask = (wdf["start"] >= calib_start) & (wdf["start"] < calib_end)
        test_mask = (wdf["start"] >= test_start) & (wdf["start"] < test_end)
        if int(train_mask.sum()) < 10:
            raise RuntimeError("not enough training windows (need >= 10)")
        if int(calib_mask.sum()) == 0:
            calib_mask = train_mask

        train_idx = np.where(train_mask.values)[0]
        calib_idx = np.where(calib_mask.values)[0]
        test_idx = np.where(test_mask.values)[0]

        baselines = compute_baselines(wdf.iloc[train_idx])

        # ---- primary model: Isolation Forest ----------------------------------
        pre = fit_preprocessor(X_all[train_idx])
        X_train = transform(pre, X_all[train_idx])
        X_calib = transform(pre, X_all[calib_idx])
        X_test = transform(pre, X_all[test_idx])

        model = train_isolation_forest(X_train, settings.model_seed,
                                       settings.iforest_estimators,
                                       settings.iforest_contamination)
        calib_sorted = np.sort(raw_scores(model, X_calib))
        raw = raw_scores(model, X_test)
        norm = normalize_scores(calib_sorted, raw)

        # persist artifact + model version
        mv_id = new_id("mdl")
        artifact = {
            "feature_names": FEATURE_NAMES,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "preprocessor": pre, "model": model, "calib_sorted": calib_sorted,
            "baselines": baselines, "employee_meta": employee_meta,
            "seed": settings.model_seed, "alert_threshold": settings.alert_threshold,
        }
        artifact_path = settings.model_dir / f"{mv_id}.joblib"
        joblib.dump(artifact, artifact_path)

        mv = ModelVersion(
            id=mv_id, algorithm="isolation_forest",
            parameters={"n_estimators": settings.iforest_estimators,
                        "contamination": settings.iforest_contamination,
                        "window_minutes": settings.window_minutes,
                        "stride_minutes": settings.stride_minutes,
                        "seed": settings.model_seed},
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            artifact_path=str(artifact_path), artifact_sha256=sha256_file(artifact_path),
            training_dataset_id=dataset_id)
        db.add(mv)
        run.model_version_id = mv_id
        run.threshold_config = {"alert_threshold": settings.alert_threshold,
                                "high_band": settings.high_band,
                                "medium_band": settings.medium_band}

        # persist windows
        db.add_all([FeatureWindow(
            id=w.window_id, dataset_id=dataset_id, employee_id=w.employee_id,
            window_start=w.start, window_end=w.end,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            features=w.features, source_event_ids=w.event_ids) for w in windows])
        db.commit()

        # ---- score test windows -> alerts ---------------------------------------
        test_windows = [windows[i] for i in test_idx]
        scored_rows, alert_items = [], []
        alerted = np.zeros(len(test_windows), dtype=int)
        for k, w in enumerate(test_windows):
            pscore = priority_score(float(norm[k]), w.features)
            band = priority_band(pscore)
            is_alert = bool(norm[k] >= settings.alert_threshold)
            alerted[k] = int(is_alert)
            scored_rows.append(ScoredWindow(
                id=new_id("sw"), run_id=run.id, window_id=w.window_id,
                employee_id=w.employee_id, window_start=w.start, window_end=w.end,
                raw_score=float(raw[k]), normalized_score=float(norm[k]),
                priority_score=float(pscore), priority_band=band, is_alert=is_alert))
            if is_alert:
                alert_items.append((w, float(raw[k]), float(norm[k]), float(pscore), band))
        db.add_all(scored_rows)
        db.commit()

        # ---- explanations -------------------------------------------------------
        for (w, r_raw, r_norm, pscore, band) in alert_items:
            alert = Alert(id=new_id("al"), run_id=run.id, window_id=w.window_id,
                          dataset_id=dataset_id, employee_id=w.employee_id,
                          window_start=w.start, window_end=w.end, raw_score=r_raw,
                          normalized_score=r_norm, priority_score=pscore,
                          priority_band=band)
            db.add(alert)
            db.flush()
            db.add(explain_window(artifact, w, events, alert.id))
        db.commit()

        # ---- evaluation (labels used here ONLY) -----------------------------------
        scenarios = manifest.get("scenarios", [])
        metrics = evaluate(test_windows, norm, alerted, scenarios) if scenarios else \
            {"note": "no label manifest; evaluation skipped"}
        metrics["alert_threshold"] = settings.alert_threshold

        # robust z-score baseline (§8.4)
        calib_windows = [windows[i] for i in calib_idx]
        z_test = baseline_zscore.composite_scores(test_windows, baselines, employee_meta)
        z_calib_sorted = np.sort(
            baseline_zscore.composite_scores(calib_windows, baselines, employee_meta))
        z_norm = normalize_scores(z_calib_sorted, z_test)
        z_alerted = (z_norm >= settings.alert_threshold).astype(int)
        metrics["zscore_baseline"] = evaluate(test_windows, z_norm, z_alerted, scenarios) \
            if scenarios else {"note": "no labels"}

        # optional autoencoder comparison (FR-19)
        if settings.enable_autoencoder and autoencoder.is_available():
            ae = autoencoder.train_autoencoder(X_train, seed=settings.model_seed)
            ae_calib_sorted = np.sort(autoencoder.reconstruction_errors(ae, X_calib))
            ae_norm = normalize_scores(ae_calib_sorted,
                                       autoencoder.reconstruction_errors(ae, X_test))
            ae_alerted = (ae_norm >= settings.alert_threshold).astype(int)
            ae_metrics = evaluate(test_windows, ae_norm, ae_alerted, scenarios) \
                if scenarios else {"note": "no labels"}
            ae_path = settings.model_dir / f"ae_{run.id}.joblib"
            joblib.dump(ae, ae_path)
            ae_metrics["artifact_path"] = str(ae_path)
            ae_metrics["artifact_sha256"] = sha256_file(ae_path)
            ae_metrics["final_train_loss"] = ae["final_loss"]
            metrics["autoencoder"] = ae_metrics
        else:
            metrics["autoencoder"] = {"note": "skipped (torch not installed or disabled)"}

        # ---- experiment tracking (FR-18) ------------------------------------------
        flat = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
        for sub_key in ("zscore_baseline", "autoencoder"):
            sub = metrics.get(sub_key) or {}
            for k, v in sub.items():
                if isinstance(v, (int, float)):
                    flat[f"{sub_key}_{k}"] = v
        metrics["tracking"] = tracking.log_run(
            dataset_id,
            params={"algorithm": "isolation_forest", **mv.parameters,
                    "alert_threshold": settings.alert_threshold},
            metrics=flat, artifact_path=str(artifact_path), run_name=run.id)

        run.metrics = metrics
        run.status = "completed"
        run.completed_at = utcnow()
        db.commit()
        return run.id
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(ModelRun, run.id)
        run.status = "failed"
        run.error = str(exc)
        db.commit()
        raise
    finally:
        db.close()


def queue_analysis(db, dataset_id: str) -> ModelRun:
    run = ModelRun(id=new_id("run"), dataset_id=dataset_id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run