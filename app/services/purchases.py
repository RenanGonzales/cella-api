"""Archived shopping lists: purchase history and price fine-tuning at home."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Market,
    Product,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
)
from app.schemas.shopping import PurchaseDetail, PurchaseItemOut, PurchaseSummary
from app.services.shopping_flow import line_total_cents


def get_purchase(db: Session, household_id: uuid.UUID, purchase_id: uuid.UUID) -> ShoppingList:
    purchase = db.get(ShoppingList, purchase_id)
    if (
        purchase is None
        or purchase.household_id != household_id
        or purchase.status != ShoppingListStatus.ARCHIVED
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found")
    return purchase


def _items(db: Session, purchase_id: uuid.UUID) -> list[tuple[ShoppingListItem, Product]]:
    return db.execute(
        select(ShoppingListItem, Product)
        .join(Product, Product.id == ShoppingListItem.product_id)
        .where(ShoppingListItem.shopping_list_id == purchase_id)
        .order_by(Product.name)
    ).all()


def _summary_fields(db: Session, purchase: ShoppingList, rows) -> dict:
    bought = [item for item, _ in rows if item.status == ShoppingListItemStatus.CHECKED]
    totals = [line_total_cents(item.quantity_bought, item.unit_price_cents) for item in bought]
    market = db.get(Market, purchase.market_id) if purchase.market_id else None
    return {
        "id": purchase.id,
        "market_id": purchase.market_id,
        "market_name": market.name if market else None,
        "started_at": purchase.started_at,
        "completed_at": purchase.completed_at,
        "items_bought": len(bought),
        "items_without_price": sum(total is None for total in totals),
        "total_cents": sum(total for total in totals if total is not None),
    }


def summarize(db: Session, purchase: ShoppingList) -> PurchaseSummary:
    return PurchaseSummary(**_summary_fields(db, purchase, _items(db, purchase.id)))


def list_purchases(db: Session, household_id: uuid.UUID, limit: int) -> list[PurchaseSummary]:
    purchases = db.scalars(
        select(ShoppingList)
        .where(
            ShoppingList.household_id == household_id,
            ShoppingList.status == ShoppingListStatus.ARCHIVED,
        )
        .order_by(ShoppingList.completed_at.desc())
        .limit(limit)
    ).all()
    return [summarize(db, purchase) for purchase in purchases]


def purchase_detail(db: Session, purchase: ShoppingList) -> PurchaseDetail:
    rows = _items(db, purchase.id)
    return PurchaseDetail(
        **_summary_fields(db, purchase, rows),
        items=[
            PurchaseItemOut(
                id=item.id,
                product_id=product.id,
                name=product.name,
                brand=product.brand,
                unit=product.unit,
                status=item.status,
                quantity_bought=item.quantity_bought,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=line_total_cents(item.quantity_bought, item.unit_price_cents),
            )
            for item, product in rows
        ],
    )


def set_price(
    db: Session, purchase: ShoppingList, item_id: uuid.UUID, unit_price_cents: int | None
) -> None:
    item = db.get(ShoppingListItem, item_id)
    if item is None or item.shopping_list_id != purchase.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase item not found")
    if item.status != ShoppingListItemStatus.CHECKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only bought items have a price")
    item.unit_price_cents = unit_price_cents
