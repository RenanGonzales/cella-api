import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models import Market, Product, ShoppingList, ShoppingListItem
from app.schemas.shopping import (
    CheckoutResponse,
    ShoppingListItemCreate,
    ShoppingListItemUpdate,
    ShoppingListOut,
    SplitRequest,
    StartShoppingRequest,
)
from app.services.catalog import get_owned
from app.services.purchases import get_purchase, summarize
from app.services.shopping import (
    ACTIVE_STATUSES,
    build_list_view,
    find_item,
    get_or_create_active_list,
)
from app.services.shopping_flow import (
    cancel_shopping,
    checkout,
    split_list,
    start_shopping,
    update_item_in_store,
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
    user: CurrentUser,
    db: DbSession,
    market_id: uuid.UUID | None = None,
    mine: bool = False,
) -> ShoppingListOut:
    """The active list, grouped by a market's corridors in walking order (`market_id`, or
    the market chosen when shopping started) or else by category.

    With `mine=true`, only the items assigned to the logged-in person: their route.
    """
    if market_id is not None:
        get_owned(db, Market, market_id, user.household_id, "Market")
    return build_list_view(db, user.household_id, market_id, user.id if mine else None)


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
    """Change the quantity to buy (automatic updates never lower it afterwards) or, while
    shopping, mark the item as checked / not found and change who picks it up."""
    item = _active_item(db, user, item_id)
    update_item_in_store(db, user, item, body.model_dump(exclude_unset=True))
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    db.delete(_active_item(db, user, item_id))
    db.commit()


@router.post("/start", response_model=ShoppingListOut)
def start(body: StartShoppingRequest, user: CurrentUser, db: DbSession) -> ShoppingListOut:
    """At the market: choose it, and the list is sorted by its corridors from now on."""
    start_shopping(db, user, body.market_id)
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.post("/cancel", response_model=ShoppingListOut)
def cancel(user: CurrentUser, db: DbSession) -> ShoppingListOut:
    """Leave without buying: the list goes back to open and nothing is lost."""
    cancel_shopping(db, user)
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.post("/split", response_model=ShoppingListOut)
def split(body: SplitRequest, user: CurrentUser, db: DbSession) -> ShoppingListOut:
    """Split the route: each person gets a block of neighboring corridors, balanced by
    number of items. A corridor is never split; items can be reassigned by hand."""
    split_list(db, user, body.user_ids)
    db.commit()
    return build_list_view(db, user.household_id, None)


@router.post("/checkout", response_model=CheckoutResponse)
def finish(user: CurrentUser, db: DbSession) -> CheckoutResponse:
    """Finish the purchase: checked items go into stock, the list is archived, and what
    was not found moves to a new list. Prices can be filled in later in /purchases."""
    purchase, bought, carried = checkout(db, user)
    purchase_id = purchase.id
    db.commit()
    summary = summarize(db, get_purchase(db, user.household_id, purchase_id))
    return CheckoutResponse(
        purchase_id=purchase_id,
        items_bought=bought,
        items_carried_over=carried,
        total_cents=summary.total_cents,
        items_without_price=summary.items_without_price,
    )
