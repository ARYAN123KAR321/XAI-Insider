"""Create schema and seed demo users. Run: python -m app.db.migrate"""
from __future__ import annotations

from app.config.settings import get_settings
from app.db.database import SessionLocal, engine
from app.db.models import Base   # <-- Fixed import here
from app.db import models  # noqa: F401  (register mappers)
from app.security.auth import hash_password
from app.util.ids import new_id


def init_db() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        demo_users = [
            ("admin", settings.demo_admin_password, "admin"),
            ("analyst", settings.demo_analyst_password, "analyst"),
            ("reviewer", settings.demo_reviewer_password, "reviewer"),
        ]
        for username, password, role in demo_users:
            existing = db.query(models.User).filter_by(username=username).first()
            if not existing:
                db.add(models.User(
                    id=new_id("usr"), username=username,
                    password_hash=hash_password(password), role=role,
                ))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized; demo users created (admin/analyst/reviewer).")