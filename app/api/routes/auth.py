from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AppSettings, DbSession
from app.core.config import Settings
from app.core.demo import DEMO_LOGIN_EMAIL
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.invite import generate_invite_code, normalize_invite_code
from app.models import Household, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.catalog import add_default_catalog

router = APIRouter(prefix="/auth", tags=["auth"])

INVITE_CODE_ATTEMPTS = 5


def _token_response(user: User, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_expire_days * 24 * 60 * 60,
    )


def _create_household(db: DbSession, name: str) -> Household:
    """Create a household with a unique invite code and the default storage areas and categories."""
    for _ in range(INVITE_CODE_ATTEMPTS):
        code = generate_invite_code()
        if db.scalar(select(Household.id).where(Household.invite_code == code)) is None:
            household = Household(name=name, invite_code=code)
            db.add(household)
            db.flush()
            add_default_catalog(db, household.id)
            return household
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not create household")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    """Create an account and log in. Creates a new household or joins one by invite code."""
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    if body.invite_code is not None:
        household = db.scalar(
            select(Household).where(
                Household.invite_code == normalize_invite_code(body.invite_code)
            )
        )
        if household is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite code not found")
    else:
        household = _create_household(db, body.household_name)

    user = User(
        household_id=household.id,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two sign-ups with the same email at the same time: the unique index decides.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None

    return _token_response(user, settings)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    """Log in with email and password.

    The error is the same for an unknown email and a wrong password, so the endpoint
    does not reveal which emails are registered.
    """
    user = db.scalar(select(User).where(User.email == body.email))
    password_hash = user.password_hash if user is not None else None

    if not verify_password(body.password, password_hash) or user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user, settings)


@router.post("/demo", response_model=TokenResponse)
def demo_login(db: DbSession, settings: AppSettings) -> TokenResponse:
    """Log in as the demo household member, no password needed. Only when DEMO_ENABLED=true."""
    if not settings.demo_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    user = db.scalar(select(User).where(User.email == DEMO_LOGIN_EMAIL))
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Demo data is not loaded")
    return _token_response(user, settings)
