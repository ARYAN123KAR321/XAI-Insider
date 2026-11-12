from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Point the app at temp storage + a temp SQLite DB and rebind all sessions."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ENABLE_MLFLOW", "false")
    monkeypatch.setenv("ENABLE_AUTOENCODER", "false")
    monkeypatch.setenv("EMBEDDED_WORKER", "false")

    from app.config import settings as settings_mod
    s = settings_mod.reload_settings()
    s.data_dir = tmp_path / "data"
    s.model_dir = tmp_path / "models"
    s.ensure_dirs()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import database
    old_session_factory = database.SessionLocal
    database.engine = create_engine(s.database_url,
                                    connect_args={"check_same_thread": False})
    database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False,
                                         expire_on_commit=False, future=True)

    from app.db.database import Base
    from app.db import models  # noqa: F401
    Base.metadata.create_all(database.engine)

    # Rebind SessionLocal in any module that imported it earlier
    for mod in list(sys.modules.values()):
        if getattr(mod, "SessionLocal", None) is old_session_factory:
            mod.SessionLocal = database.SessionLocal

    from app.db.models import User
    from app.security.auth import hash_password
    from app.util.ids import new_id
    db = database.SessionLocal()
    for uname, role in (("tester", "analyst"), ("rev", "reviewer")):
        db.add(User(id=new_id("usr"), username=uname, password_hash=hash_password("pw"),
                    role=role))
    db.commit()
    db.close()
    yield s