import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.stock import needs_restock, quantity_needed
from app.models import (
    Category,
    ConsumptionEvent,
    Corridor,
    CorridorCategory,
    Product,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
    User,
)
from app.schemas.shopping import ShoppingListGroup, ShoppingListItemOut, ShoppingListOut
from app.services.catalog import last_purchase_subquery

ACTIVE_STATUSES = (ShoppingListStatus.OPEN, ShoppingListStatus.SHOPPING)
UNDO_WINDOW = timedelta(minutes=10)
OTHER_GROUP = "Other"


# --- Active list ----------------------------------------------------------


def find_active_list(
    db: Session, household_id: uuid.UUID, lock: bool = False
) -> ShoppingList | None:
    """The household's open or in-progress list. With `lock`, the row is locked.

    Lock order everywhere is: active list first, then products (sorted by id). Using one
    order in every transaction prevents deadlocks between consume and checkout.
    """
    query = select(ShoppingList).where(
        ShoppingList.household_id == household_id, ShoppingList.status.in_(ACTIVE_STATUSES)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def get_or_create_active_list(db: Session, household_id: uuid.UUID) -> ShoppingList:
    """The household's open or in-progress list, created on first use.

    Two first-time consumes at the same moment could both try to create a list; the
    partial unique index lets only one win, and the other reuses it.
    """
    active = find_active_list(db, household_id)
    if active is not None:
        return active
    try:
        with db.begin_nested():
            active = ShoppingList(household_id=household_id, status=ShoppingListStatus.OPEN)
            db.add(active)
    except IntegrityError:
        active = find_active_list(db, household_id)
    return active


def find_item(db: Session, shopping_list_id: uuid.UUID, product_id: uuid.UUID):
    return db.scalar(
        select(ShoppingListItem).where(
            ShoppingListItem.shopping_list_id == shopping_list_id,
            ShoppingListItem.product_id == product_id,
        )
    )


# --- Locking --------------------------------------------------------------


def lock_product(db: Session, product_id: uuid.UUID, household_id: uuid.UUID) -> Product:
    """Load a product with a row lock (SELECT ... FOR UPDATE).

    Concurrent consumes of the same product wait for each other instead of both reading
    the same stock and overwriting each other's result (a lost update).
    """
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.household_id == household_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


# --- Automatic list updates -----------------------------------------------


def _needed(product: Product) -> Decimal:
    return quantity_needed(product.ideal_quantity, product.current_quantity, product.consume_step)


def _needs_restock(product: Product) -> bool:
    return needs_restock(product.current_quantity, product.min_quantity, product.ideal_quantity)


def add_if_needs_restock(db: Session, product: Product) -> bool:
    """After a consume: once stock reaches the minimum, put the product on the list
    (or raise its quantity) to get back to the ideal.

    Returns True when the product is on the active list afterwards. Never lowers a
    quantity a person chose, and never touches an item already in the cart.
    """
    if not _needs_restock(product):
        active = find_active_list(db, product.household_id)
        return active is not None and find_item(db, active.id, product.id) is not None

    needed = _needed(product)
    active = get_or_create_active_list(db, product.household_id)
    item = find_item(db, active.id, product.id)
    if item is None:
        db.add(
            ShoppingListItem(
                shopping_list_id=active.id, product_id=product.id, quantity_needed=needed
            )
        )
    elif item.status != ShoppingListItemStatus.CHECKED:
        item.quantity_needed = max(item.quantity_needed, needed)
        if item.status == ShoppingListItemStatus.NOT_FOUND:
            item.status = ShoppingListItemStatus.PENDING
    return True


def shrink_after_undo(db: Session, product: Product) -> None:
    """After an undo: lower an automatic pending item, or remove it when stock is back
    above the minimum."""
    active = find_active_list(db, product.household_id)
    if active is None:
        return
    item = find_item(db, active.id, product.id)
    if item is None or item.added_manually or item.status != ShoppingListItemStatus.PENDING:
        return

    if not _needs_restock(product):
        db.delete(item)
    else:
        item.quantity_needed = _needed(product)


# --- Consume and undo -----------------------------------------------------


def consume_product(
    db: Session, user: User, product_id: uuid.UUID, quantity: Decimal | None
) -> tuple[Product, ConsumptionEvent | None, Decimal, bool]:
    """Remove stock, record what was really removed and update the shopping list.

    The caller commits. Returns (product, event, consumed, on_list).
    """
    find_active_list(db, user.household_id, lock=True)  # lock order: list, then product
    product = lock_product(db, product_id, user.household_id)
    if product.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product is archived")

    requested = quantity if quantity is not None else product.consume_step
    # Stock never goes below zero; the event records only what was actually removed,
    # so consumption history (and future autonomy forecasts) are not inflated.
    consumed = min(requested, product.current_quantity)
    product.current_quantity -= consumed

    event = None
    if consumed > 0:
        event = ConsumptionEvent(product_id=product.id, user_id=user.id, quantity=consumed)
        db.add(event)

    on_list = add_if_needs_restock(db, product)
    db.flush()
    return product, event, consumed, on_list


def undo_consumption(db: Session, user: User, event_id: uuid.UUID) -> tuple[Product, Decimal]:
    """Give back the stock of a recent consumption by the same user and delete the event."""
    event = db.get(ConsumptionEvent, event_id)
    product = db.get(Product, event.product_id) if event is not None else None
    if event is None or product is None or product.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consumption not found")
    if event.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only who consumed can undo")

    consumed_at = event.consumed_at
    if consumed_at.tzinfo is None:
        consumed_at = consumed_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - consumed_at > UNDO_WINDOW:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too late to undo")

    find_active_list(db, user.household_id, lock=True)  # lock order: list, then product
    product = lock_product(db, product.id, user.household_id)
    product.current_quantity += event.quantity
    restored = event.quantity
    # A mistaken tap is not real consumption, so it leaves no trace in the history.
    db.delete(event)
    shrink_after_undo(db, product)
    db.flush()
    return product, restored


# --- List view ------------------------------------------------------------


def build_list_view(
    db: Session,
    household_id: uuid.UUID,
    market_id: uuid.UUID | None,
    only_user_id: uuid.UUID | None = None,
) -> ShoppingListOut:
    """Active list grouped by the market's corridors (walking order), or by category.

    While shopping, the chosen market is used when no `market_id` is given. Categories
    without a corridor in that market go to an "Other" group at the end. With
    `only_user_id`, only the items assigned to that person are returned (their route).
    """
    active = find_active_list(db, household_id)
    if active is not None and market_id is None:
        market_id = active.market_id
    if active is None:
        return ShoppingListOut(
            id=None,
            status=None,
            market_id=None,
            sorted_by_market_id=market_id,
            item_count=0,
            groups=[],
        )

    last = last_purchase_subquery()
    query = (
        select(ShoppingListItem, Product, Category, last.c.unit_price_cents)
        .join(Product, Product.id == ShoppingListItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .outerjoin(last, last.c.product_id == Product.id)
        .where(ShoppingListItem.shopping_list_id == active.id)
    )
    if only_user_id is not None:
        query = query.where(ShoppingListItem.assigned_user_id == only_user_id)

    if market_id is not None:
        query = (
            query.add_columns(Corridor)
            .outerjoin(
                CorridorCategory,
                and_(
                    CorridorCategory.category_id == Category.id,
                    CorridorCategory.market_id == market_id,
                ),
            )
            .outerjoin(Corridor, Corridor.id == CorridorCategory.corridor_id)
            .order_by(Corridor.position.asc().nulls_last(), Product.name)
        )
    else:
        query = query.order_by(Category.name, Product.name)

    groups: OrderedDict[object, ShoppingListGroup] = OrderedDict()
    item_count = 0
    for row in db.execute(query).all():
        item, product, category, last_price = row[0], row[1], row[2], row[3]
        corridor = row[4] if market_id is not None else None

        if market_id is not None:
            key = corridor.id if corridor is not None else None
            name = corridor.name if corridor is not None else OTHER_GROUP
            corridor_id = key
        else:
            key, name, corridor_id = category.id, category.name, None

        if key not in groups:
            groups[key] = ShoppingListGroup(corridor_id=corridor_id, name=name, items=[])
        groups[key].items.append(
            ShoppingListItemOut(
                id=item.id,
                product_id=product.id,
                name=product.name,
                brand=product.brand,
                category=category.name,
                unit=product.unit,
                quantity_needed=item.quantity_needed,
                quantity_bought=item.quantity_bought,
                status=item.status,
                added_manually=item.added_manually,
                assigned_user_id=item.assigned_user_id,
                last_price_cents=last_price,
                current_quantity=product.current_quantity,
                min_quantity=product.min_quantity,
                ideal_quantity=product.ideal_quantity,
            )
        )
        item_count += 1

    # The "Other" group (key None) always goes last.
    if None in groups:
        groups.move_to_end(None)

    return ShoppingListOut(
        id=active.id,
        status=active.status,
        market_id=active.market_id,
        sorted_by_market_id=market_id,
        item_count=item_count,
        groups=list(groups.values()),
    )
