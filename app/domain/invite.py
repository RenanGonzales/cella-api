import secrets

# No 0/O or 1/I/L: codes are typed by hand from one phone to another.
INVITE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVITE_LENGTH = 8


def generate_invite_code() -> str:
    """Random household invite code, e.g. K7MX4QPA (~31^8, about 850 billion options)."""
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def normalize_invite_code(code: str) -> str:
    """Accept codes typed in lowercase or with spaces."""
    return code.replace(" ", "").upper()
