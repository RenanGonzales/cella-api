from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import Household, User
from app.schemas.auth import FeaturesOut, HouseholdOut, MemberOut, MeResponse
from app.services.receipts import ai_reading_allowed

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
def read_me(user: CurrentUser, db: DbSession, settings: AppSettings) -> MeResponse:
    """The logged-in user, their household, its invite code, its members and the features
    this account can use."""
    household = db.get(Household, user.household_id)
    members = db.scalars(
        select(User).where(User.household_id == user.household_id).order_by(User.created_at)
    ).all()

    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        household=HouseholdOut(
            id=household.id,
            name=household.name,
            invite_code=household.invite_code,
            members=[MemberOut(id=member.id, name=member.name) for member in members],
        ),
        features=FeaturesOut(
            receipt_ai=ai_reading_allowed(settings, user, household),
            is_demo=household.demo_expires_at is not None,
        ),
    )
