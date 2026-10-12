import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.defaults import DEFAULT_CATEGORIES, DEFAULT_STORAGE_AREAS
from app.models import (
    Category,
    Market,
    Product,
    ShoppingList,
    ShoppingListItem,
    ShoppingListStatus,
    StorageArea,
)


def add_default_catalog(db: Session, household_id: uuid.UUID) -> None:
    """Give a new household the default storage areas and categories."""
    db.add_all(
        StorageArea(household_id=household_id, name=name, position=position)
        for position, name in enumerate(DEFAULT_STORAGE_AREAS)
    )
    db.add_all(Category(household_id=household_id, name=name) for name in DEFAULT_CATEGORIES)


def get_owned[T: (StorageArea, Category, Product, Market)](
    db: Session, model: type[T], object_id: uuid.UUID, household_id: uuid.UUID, label: str
) -> T:
    """Load a row that belongs to the household, or answer 404.

    Rows of other households also get 404 (not 403), so ids from another household
    cannot even be confirmed to exist.
    """
    row = db.get(model, object_id)
    if row is None or row.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return row


def name_taken(
    db: Session,
    model: type[StorageArea] | type[Category],
    household_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive name check inside a household."""
    query = select(model.id).where(
        model.household_id == household_id, func.lower(model.name) == name.lower()
    )
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    return db.scalar(query) is not None


def last_purchase_subquery():
    """Latest priced purchase of each product: (product_id, unit_price_cents, purchased_at)."""
    ranked = (
        select(
            ShoppingListItem.product_id,
            ShoppingListItem.unit_price_cents,
            ShoppingList.completed_at.label("purchased_at"),
            func.row_number()
            .over(
                partition_by=ShoppingListItem.product_id,
                order_by=ShoppingList.completed_at.desc(),
            )
            .label("rank"),
        )
        .join(ShoppingList, ShoppingList.id == ShoppingListItem.shopping_list_id)
        .where(
            ShoppingList.status == ShoppingListStatus.ARCHIVED,
            ShoppingListItem.unit_price_cents.is_not(None),
        )
        .subquery()
    )
    return (
        select(ranked.c.product_id, ranked.c.unit_price_cents, ranked.c.purchased_at)
        .where(ranked.c.rank == 1)
        .subquery()
    )


def products_with_last_price(household_id: uuid.UUID) -> Select:
    """Products of a household, each with its last price paid and purchase date."""
    last = last_purchase_subquery()
    return (
        select(Product, last.c.unit_price_cents, last.c.purchased_at)
        .outerjoin(last, last.c.product_id == Product.id)
        .where(Product.household_id == household_id)
    )
