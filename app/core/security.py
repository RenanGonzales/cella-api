import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings

# bcrypt only looks at the first 72 bytes of a password and silently ignores the rest.
# Passwords are validated against this limit instead of being truncated without notice.
BCRYPT_MAX_BYTES = 72

# Hash checked when the email does not exist, so a failed login takes the same time
# whether or not the account exists (no user enumeration by timing).
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(
    user_id: uuid.UUID, settings: Settings, lifetime: timedelta | None = None
) -> str:
    """Signed token for the user; `lifetime` overrides the default (e.g. shorter demo sessions)."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + (lifetime or timedelta(days=settings.access_token_expire_days)),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    """Return the user id inside a valid token, or None if it is invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
