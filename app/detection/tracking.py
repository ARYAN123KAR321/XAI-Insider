"""Experiment tracking: MLflow when available (FR-18), safe no-op otherwise."""
from __future__ import annotations

from app.config.settings import get_settings


def log_run(dataset_id: str, params: dict, metrics: dict,
            artifact_path: str | None = None, run_name: str | None = None) -> dict:
    s = get_settings()
    if not s.enable_mlflow:
        return {"backend": "disabled"}
    try:
        import mlflow
        mlflow.set_tracking_uri(s.mlflow_tracking_uri)
        mlflow.set_experiment("xai-insider")
        with mlflow.start_run(run_name=run_name or "analysis-run"):
            mlflow.log_params({**{k: str(v) for k, v in params.items()},
                               "dataset_id": dataset_id})
            for k, v in (metrics or {}).items():
                if isinstance(v, (int, float)) and v is not None:
                    mlflow.log_metric(k, float(v))
            if artifact_path:
                try:
                    mlflow.log_artifact(str(artifact_path))
                except Exception:  # noqa: BLE001 - artifact logging is best-effort
                    pass
        return {"backend": "mlflow", "tracking_uri": s.mlflow_tracking_uri}
    except Exception as exc:  # noqa: BLE001
        return {"backend": "unavailable", "error": str(exc)}