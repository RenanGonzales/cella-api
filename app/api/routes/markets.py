import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Market, ShoppingList
from app.schemas.market import LayoutIn, LayoutOut, MarketCreate, MarketOut, MarketUpdate
from app.services.catalog import get_owned
from app.services.market import corridor_counts, read_layout, replace_layout

router = APIRouter(prefix="/markets", tags=["markets"])

LABEL = "Market"


def _to_out(market: Market, corridor_count: int) -> MarketOut:
    return MarketOut(
        id=market.id,
        name=market.name,
        chain=market.chain,
        address=market.address,
        corridor_count=corridor_count,
        archived_at=market.archived_at,
    )


def _out(db: DbSession, market: Market) -> MarketOut:
    return _to_out(market, corridor_counts(db, [market.id]).get(market.id, 0))


@router.get("", response_model=list[MarketOut])
def list_markets(
    user: CurrentUser, db: DbSession, include_archived: bool = False
) -> list[MarketOut]:
    query = select(Market).where(Market.household_id == user.household_id)
    if not include_archived:
        query = query.where(Market.archived_at.is_(None))
    markets = db.scalars(query.order_by(Market.name)).all()

    counts = corridor_counts(db, [market.id for market in markets])
    return [_to_out(market, counts.get(market.id, 0)) for market in markets]


@router.post("", response_model=MarketOut, status_code=status.HTTP_201_CREATED)
def create_market(body: MarketCreate, user: CurrentUser, db: DbSession) -> MarketOut:
    market = Market(household_id=user.household_id, **body.model_dump())
    db.add(market)
    db.commit()
    return _to_out(market, 0)


@router.get("/{market_id}", response_model=MarketOut)
def read_market(market_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MarketOut:
    return _out(db, get_owned(db, Market, market_id, user.household_id, LABEL))


@router.patch("/{market_id}", response_model=MarketOut)
def update_market(
    market_id: uuid.UUID, body: MarketUpdate, user: CurrentUser, db: DbSession
) -> MarketOut:
    """Change only the fields sent. `chain` and `address` accept null to clear them."""
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(market, field, value)
    db.commit()
    return _out(db, market)


@router.delete("/{market_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_market(market_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    """Delete a market never used for shopping. Markets with history can only be archived."""
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    used = db.scalar(select(func.count()).where(ShoppingList.market_id == market.id))
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{LABEL} has purchase history; archive it instead to keep its prices",
        )
    db.delete(market)
    db.commit()


@router.post("/{market_id}/archive", response_model=MarketOut)
def archive_market(market_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MarketOut:
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    if market.archived_at is None:
        market.archived_at = datetime.now(UTC)
        db.commit()
    return _out(db, market)


@router.post("/{market_id}/restore", response_model=MarketOut)
def restore_market(market_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MarketOut:
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    market.archived_at = None
    db.commit()
    return _out(db, market)


@router.get("/{market_id}/layout", response_model=LayoutOut)
def get_layout(market_id: uuid.UUID, user: CurrentUser, db: DbSession) -> LayoutOut:
    """Corridors in walking order with their categories, plus categories with no corridor."""
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    return read_layout(db, market)


@router.put("/{market_id}/layout", response_model=LayoutOut)
def put_layout(market_id: uuid.UUID, body: LayoutIn, user: CurrentUser, db: DbSession) -> LayoutOut:
    """Save the whole layout at once: either everything is saved or nothing is."""
    market = get_owned(db, Market, market_id, user.household_id, LABEL)
    replace_layout(db, market, body)
    db.commit()
    return read_layout(db, market)
