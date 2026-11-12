"""Reset the demo: wipe database rows and generated/exported artifacts.

Usage: python scripts/reset_demo.py --yes
"""
from __future__ import annotations

import argparse
import shutil

from app.config.settings import get_settings
from app.db.database import Base, SessionLocal, engine
from app.db.migrate import init_db


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--yes", action="store_true", required=True,
                   help="confirm destructive reset")
    p.parse_args()

    settings = get_settings()
    Base.metadata.drop_all(engine)
    for d in (settings.generated_dir, settings.cases_dir, settings.exports_dir,
              settings.model_dir):
        shutil.rmtree(d, ignore_errors=True)
    settings.ensure_dirs()
    init_db()
    print("Demo reset complete. Schema recreated; demo users reseeded.")


if __name__ == "__main__":
    main()