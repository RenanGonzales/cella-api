from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.stats import ConsumptionSummary, MonthSpending
from app.services.stats import monthly_spending, recent_consumption

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/spending", response_model=list[MonthSpending])
def read_spending(
    user: CurrentUser,
    db: DbSession,
    months: int = Query(6, ge=1, le=24),
    tz: str = Query("UTC", max_length=64, description="IANA time zone that defines the months"),
) -> list[MonthSpending]:
    """What was paid per month, oldest first, months without purchases included as zero."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown time zone") from None
    return monthly_spending(db, user.household_id, months, zone)


@router.get("/consumption", response_model=ConsumptionSummary)
def read_consumption(
    user: CurrentUser, db: DbSession, days: int = Query(7, ge=1, le=90)
) -> ConsumptionSummary:
    """What was used in the last days, most used first."""
    return recent_consumption(db, user.household_id, days)
