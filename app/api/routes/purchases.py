import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.shopping import PurchaseDetail, PurchaseItemUpdate, PurchaseSummary
from app.services.purchases import get_purchase, list_purchases, purchase_detail, set_price

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get("", response_model=list[PurchaseSummary])
def read_purchases(
    user: CurrentUser, db: DbSession, limit: int = Query(20, ge=1, le=100)
) -> list[PurchaseSummary]:
    """Past purchases, newest first, with total spent and items still without a price."""
    return list_purchases(db, user.household_id, limit)


@router.get("/{purchase_id}", response_model=PurchaseDetail)
def read_purchase(purchase_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PurchaseDetail:
    return purchase_detail(db, get_purchase(db, user.household_id, purchase_id))


@router.patch("/{purchase_id}/items/{item_id}", response_model=PurchaseDetail)
def update_purchase_item(
    purchase_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PurchaseItemUpdate,
    user: CurrentUser,
    db: DbSession,
) -> PurchaseDetail:
    """Fill in or fix the price paid, per product unit. It becomes the product's last price
    when this is its most recent purchase."""
    purchase = get_purchase(db, user.household_id, purchase_id)
    set_price(db, purchase, item_id, body.unit_price_cents)
    db.commit()
    return purchase_detail(db, purchase)
