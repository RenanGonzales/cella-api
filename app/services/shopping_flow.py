"""In-store flow: start, cancel, split, check items and checkout."""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domain.split import split_corridors
from app.models import (
    Corridor,
    CorridorCategory,
    Market,
    Product,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
    User,
)
from app.services.catalog import get_owned
from app.services.shopping import find_active_list


def _require_active(db: Session, household_id: uuid.UUID) -> ShoppingList:
    active = find_active_list(db, household_id, lock=True)
    if active is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The shopping list is empty")
    return active


def _require_shopping(db: Session, household_id: uuid.UUID) -> ShoppingList:
    active = _require_active(db, household_id)
    if active.status != ShoppingListStatus.SHOPPING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start shopping first")
    return active


def _items(db: Session, shopping_list_id: uuid.UUID) -> list[ShoppingListItem]:
    return list(
        db.scalars(
            select(ShoppingListItem).where(ShoppingListItem.shopping_list_id == shopping_list_id)
        )
    )


def household_member(db: Session, household_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Household member not found")
    return user


# --- Start and cancel -----------------------------------------------------


def start_shopping(db: Session, user: User, market_id: uuid.UUID) -> ShoppingList:
    """Choose the market and mark the list as in progress (can be called again to switch)."""
    market = get_owned(db, Market, market_id, user.household_id, "Market")
    if market.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Market is archived")

    active = _require_active(db, user.household_id)
    if not _items(db, active.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "The shopping list is empty")

    if active.status == ShoppingListStatus.OPEN:
        active.started_at = datetime.now(UTC)
    active.status = ShoppingListStatus.SHOPPING
    active.market_id = market.id
    return active


def cancel_shopping(db: Session, user: User) -> ShoppingList:
    """Leave the market without buying: back to an open list, nothing is lost."""
    active = _require_shopping(db, user.household_id)
    active.status = ShoppingListStatus.OPEN
    active.market_id = None
    active.started_at = None
    for item in _items(db, active.id):
        item.status = ShoppingListItemStatus.PENDING
        item.quantity_bought = None
        item.assigned_user_id = None
    return active


# --- Split ----------------------------------------------------------------


def split_list(db: Session, user: User, user_ids: list[uuid.UUID]) -> ShoppingList:
    """Give each person a block of neighboring corridors with a balanced number of items.

    Items already in the cart keep their person. A corridor is never split.
    """
    if len(set(user_ids)) != len(user_ids):
        raise HTTPException(422, "Each person can appear only once")
    for user_id in user_ids:
        household_member(db, user.household_id, user_id)

    active = _require_shopping(db, user.household_id)

    # Items still to pick up, with the position of their corridor in this market.
    rows = db.execute(
        select(ShoppingListItem, Corridor.position)
        .join(Product, Product.id == ShoppingListItem.product_id)
        .outerjoin(
            CorridorCategory,
            and_(
                CorridorCategory.category_id == Product.category_id,
                CorridorCategory.market_id == active.market_id,
            ),
        )
        .outerjoin(Corridor, Corridor.id == CorridorCategory.corridor_id)
        .where(
            ShoppingListItem.shopping_list_id == active.id,
            ShoppingListItem.status != ShoppingListItemStatus.CHECKED,
        )
    ).all()

    # Group by corridor in walking order; "Other" (no corridor) is walked last.
    groups: dict[int | None, list[ShoppingListItem]] = {}
    for item, position in rows:
        groups.setdefault(position, []).append(item)
    order = sorted(groups, key=lambda position: (position is None, position or 0))

    assignment = split_corridors([len(groups[position]) for position in order], len(user_ids))
    for position, person in zip(order, assignment, strict=True):
        for item in groups[position]:
            item.assigned_user_id = user_ids[person]
    return active


# --- Items in the store ---------------------------------------------------


def update_item_in_store(
    db: Session, user: User, item: ShoppingListItem, changes: dict
) -> ShoppingListItem:
    """Apply in-store changes: status, quantity bought and assigned person."""
    store_fields = {"status", "quantity_bought", "assigned_user_id"} & changes.keys()
    if store_fields:
        _require_shopping(db, user.household_id)

    if "assigned_user_id" in changes:
        assigned = changes["assigned_user_id"]
        if assigned is not None:
            household_member(db, user.household_id, assigned)
        item.assigned_user_id = assigned

    if "quantity_needed" in changes:
        item.quantity_needed = changes["quantity_needed"]
        item.added_manually = True

    new_status = changes.get("status", item.status)
    if new_status == ShoppingListItemStatus.CHECKED:
        # Picked up: by default, what the list asked for.
        item.quantity_bought = changes.get("quantity_bought") or (
            item.quantity_bought or item.quantity_needed
        )
    elif "quantity_bought" in changes:
        raise HTTPException(422, "quantity_bought only applies to checked items")
    else:
        item.quantity_bought = None
    item.status = new_status
    return item


# --- Checkout -------------------------------------------------------------


def line_total_cents(quantity: Decimal | None, unit_price_cents: int | None) -> int | None:
    if quantity is None or unit_price_cents is None:
        return None
    return int((quantity * unit_price_cents).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def checkout(db: Session, user: User) -> tuple[ShoppingList, int, int]:
    """Close the purchase.

    Checked items add what was bought to stock, the list is archived, and items not
    found or still pending move to a new open list. The list row is locked first, so a
    second phone tapping "finish" at the same time gets 409 instead of adding stock twice.
    Returns (archived list, items bought, items carried over).
    """
    active = _require_shopping(db, user.household_id)
    items = _items(db, active.id)
    bought = [item for item in items if item.status == ShoppingListItemStatus.CHECKED]
    left = [item for item in items if item.status != ShoppingListItemStatus.CHECKED]

    # Lock products in id order (after the list) so concurrent requests never deadlock.
    product_ids = sorted({item.product_id for item in bought})
    products = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    for item in bought:
        products[item.product_id].current_quantity += item.quantity_bought

    active.status = ShoppingListStatus.ARCHIVED
    active.completed_at = datetime.now(UTC)
    db.flush()  # free the "one active list" slot before opening the next one

    if left:
        next_list = ShoppingList(household_id=user.household_id, status=ShoppingListStatus.OPEN)
        db.add(next_list)
        db.flush()
        db.add_all(
            ShoppingListItem(
                shopping_list_id=next_list.id,
                product_id=item.product_id,
                quantity_needed=item.quantity_needed,
                added_manually=item.added_manually,
            )
            for item in left
        )
    db.flush()
    return active, len(bought), len(left)
