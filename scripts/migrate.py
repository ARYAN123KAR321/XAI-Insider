"""Create schema and demo users. Usage: python scripts/migrate.py"""
from app.db.migrate import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized; demo users created (admin/analyst/reviewer).")