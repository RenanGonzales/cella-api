"""Create (or reset) the local demo household, with fixed logins for development.

Run with: python scripts/seed.py

The script is idempotent: it deletes this household (and everything that belongs to it)
before recreating it. The public demo does not use it: each visitor gets a private copy
(see app/services/demo.py).
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.demo import DEMO_INVITE_CODE, DEMO_PASSWORD, DEMO_USERS
from app.core.security import hash_password
from app.models import Household
from app.services.demo import PRODUCTS, build_demo_household


def reset_demo(db: Session) -> None:
    """Delete the local demo household; foreign keys cascade to everything it owns."""
    db.execute(delete(Household).where(Household.invite_code == DEMO_INVITE_CODE))
    db.flush()


def create_demo(db: Session) -> Household:
    household, _ = build_demo_household(
        db,
        invite_code=DEMO_INVITE_CODE,
        people=DEMO_USERS,
        password_hash=hash_password(DEMO_PASSWORD),
        expires_at=None,
    )
    return household


def main() -> None:
    with SessionLocal() as db, db.begin():
        reset_demo(db)
        household = create_demo(db)
        print(
            f"Demo household ready: {household.name} "
            f"({len(PRODUCTS)} products, login {DEMO_USERS[0][1]} / {DEMO_PASSWORD})"
        )


if __name__ == "__main__":
    main()
