"""Mini end-to-end: simulate -> ingest -> analyse -> explain -> counterfactual."""
from __future__ import annotations

import pytest

from app.simulator.generator import GenConfig, Generator


@pytest.fixture()
def seeded(isolated_env):
    from app.db.database import SessionLocal
    from app.db.models import Upload
    from app.ingestion.hashing import sha256_file
    from app.ingestion.pipeline import create_dataset, ingest_file_sync
    from app.simulator.generator import write_dataset
    from app.util.ids import new_id

    result = Generator(GenConfig(seed=11, days=5, employees_per_role={
        "engineering": 3, "finance": 2, "hr": 2, "operations": 2})).run()
    paths = write_dataset(isolated_env.generated_dir / "t", result)

    db = SessionLocal()
    ds = create_dataset(db, name="test-ds", seed=11)
    for key, path in paths.items():
        up = Upload(id=new_id("upl"), dataset_id=ds.id, original_name=path.name,
                    stored_path=str(path), family="manifest" if key == "manifest" else key,
                    sha256=sha256_file(path), size_bytes=path.stat().st_size)
        db.add(up)
        db.commit()
        report = ingest_file_sync(db, up)
        assert report["rejected"] == 0, report
    db.close()
    return ds.id


def test_pipeline_detects_planted_scenarios(seeded):
    from app.db.database import SessionLocal
    from app.db.models import Alert, Explanation, FeatureWindow, ModelRun, ModelVersion
    from app.detection.pipeline import run_analysis_sync

    run_id = run_analysis_sync(seeded)
    db = SessionLocal()
    run = db.get(ModelRun, run_id)
    assert run.status == "completed", run.error

    metrics = run.metrics
    assert metrics["alerts_raised"] > 0
    assert metrics["recall"] >= 0.5            # conservative bar for the tiny fixture
    assert "zscore_baseline" in metrics        # §8.4 baseline always reported

    alerts = db.query(Alert).filter_by(run_id=run_id).all()
    assert alerts
    expl = db.query(Explanation).filter_by(alert_id=alerts[0].id).first()
    assert expl is not None and expl.feature_reasons

    # counterfactual respects constraints (FR-12)
    import joblib
    from app.explainability.counterfactual import run_counterfactual
    mv = db.get(ModelVersion, run.model_version_id)
    artifact = joblib.load(mv.artifact_path)
    window = db.get(FeatureWindow, alerts[0].window_id)
    cf = run_counterfactual(artifact, window, alerts[0], requested_by="test")
    assert cf.hypothetical_score <= cf.original_score
    for change in cf.changes:
        assert change["hypothetical_value"] >= 0
        assert change["feature"] not in ("off_hours_login_ratio", "first_seen_device_flag")
    db.close()