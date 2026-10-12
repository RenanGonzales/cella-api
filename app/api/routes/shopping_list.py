import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models import Market, Product, ShoppingList, ShoppingListItem
from app.schemas.shopping import (
    ShoppingListItemCreate,
    ShoppingListItemUpdate,
    ShoppingListOut,
)
from app.services.catalog import get_owned
from app.services.shopping import (
    ACTIVE_STATUSES,
    build_list_view,
    find_item,
    get_or_create_active_list,
)

router = APIRouter(prefix="/shopping-list", tags=["shopping list"])


def _active_item(db: DbSession, user: CurrentUser, item_id: uuid.UUID) -> ShoppingListItem:
    """An item of the household's active list (archived lists are edited elsewhere)."""
    item = db.get(ShoppingListItem, item_id)
    shopping_list = db.get(ShoppingList, item.shopping_list_id) if item is not None else None
    if (
        shopping_list is None
        or shopping_list.household_id != user.household_id
        or shopping_list.status not in ACTIVE_STATUSES
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shopping list item not found")
    return item


@router.get("", response_model=ShoppingListOut)
def read_shopping_list(
    user: CurrentUser, db: DbSession, market_id: uuid.UUID | None = None
) -> ShoppingListOut:
    """The active list. With `market_id`, items are grouped by that market's corridors in
    walking order; otherwise they are grouped by category."""
    if market_id is not None:
        get_owned(db, Market, market_id, user.household_id, "Market")
    return build_list_view(db, user.household_id, market_id)


@router.post("/items", response_model=ShoppingListOut, status_code=status.HTTP_201_CREATED)
def add_item(
    body: ShoppingListItemCreate, user: CurrentUser, db: DbSession, response: Response
) -> ShoppingListOut:
    """Add a product by hand. If it is already on the list, its quantity is replaced."""
    product = get_owned(db, Product, body.product_id, user.household_id, "Product")
    if product.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product is archived")

    active = get_or_create_active_list(db, user.household_id)
    item = find_item(db, active.id, product.id)
    if item is None:
        db.add(
            ShoppingListItem(
                shopping_list_id=active.id,
                product_id=product.id,
                quantity_needed=body.quantity_needed,
                added_manually=True,
            )
        )
    else:
        item.quantity_needed = body.quantity_needed
        item.added_manually = True
        response.status_code = status.HTTP_200_OK
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.patch("/items/{item_id}", response_model=ShoppingListOut)
def update_item(
    item_id: uuid.UUID, body: ShoppingListItemUpdate, user: CurrentUser, db: DbSession
) -> ShoppingListOut:
    """Change the quantity to buy. From then on, automatic updates never lower it."""
    item = _active_item(db, user, item_id)
    item.quantity_needed = body.quantity_needed
    item.added_manually = True
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    db.delete(_active_item(db, user, item_id))
    db.commit()
