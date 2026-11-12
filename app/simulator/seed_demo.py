"""One-shot demo seeding: generate -> ingest -> analyse (synchronous).

Run:  python -m app.simulator.seed_demo
"""
from __future__ import annotations

import sys

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.db.migrate import init_db
from app.db.models import Upload
from app.detection.pipeline import run_analysis_sync
from app.ingestion.hashing import sha256_file
from app.ingestion.pipeline import create_dataset, ingest_file_sync
from app.simulator.generator import GenConfig, Generator, write_dataset
from app.util.ids import new_id, utcnow


def seed(seed: int = 42, days: int = 7) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    result = Generator(GenConfig(seed=seed, days=days)).run()
    out_dir = settings.generated_dir / f"seed-{seed}-{days}d"
    paths = write_dataset(out_dir, result)

    db = SessionLocal()
    try:
        dataset = create_dataset(db, name=result["manifest"]["dataset_name"], seed=seed)
        for key, path in paths.items():
            upload = Upload(
                id=new_id("upl"), dataset_id=dataset.id, original_name=path.name,
                stored_path=str(path), family="manifest" if key == "manifest" else key,
                sha256=sha256_file(path), size_bytes=path.stat().st_size,
                uploaded_by="seed_demo", uploaded_at=utcnow())
            db.add(upload)
            db.commit()
            report = ingest_file_sync(db, upload)
            print(f"  ingested {key:>15}: accepted={report['accepted']} "
                  f"rejected={report['rejected']} duplicates={report['duplicates']}")
        dataset_id = dataset.id
    finally:
        db.close()

    print("Running analysis pipeline...")
    run_id = run_analysis_sync(dataset_id)
    print(f"Analysis complete: run_id={run_id}")
    return dataset_id


if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    seed(s)