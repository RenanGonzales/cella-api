"""Delete expired demo copies. POST /auth/demo already does this on every new demo;
this script is for a cron job, so idle copies do not wait for the next visitor.

Run with: python scripts/cleanup_demo.py
"""

from app.core.database import SessionLocal
from app.services.demo import delete_expired_sandboxes


def main() -> None:
    with SessionLocal() as db, db.begin():
        deleted = delete_expired_sandboxes(db)
    print(f"Expired demo copies deleted: {deleted}")


if __name__ == "__main__":
    main()
