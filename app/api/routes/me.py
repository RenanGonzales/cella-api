from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Household, User
from app.schemas.auth import HouseholdOut, MemberOut, MeResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
def read_me(user: CurrentUser, db: DbSession) -> MeResponse:
    """The logged-in user, their household, its invite code and its members."""
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
    )
