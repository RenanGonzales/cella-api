"""Read-only figures for the home screen: spending per month, what was used lately,
and the price history of a product."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ConsumptionEvent,
    Market,
    Product,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
)
from app.schemas.stats import ConsumptionSummary, MonthSpending, PricePoint, ProductUse
from app.services.shopping_flow import line_total_cents


def _month_starts(now: datetime, months: int) -> list[datetime]:
    """First instant of each of the last `months` months (local time), oldest first."""
    starts = []
    year, month = now.year, now.month
    for _ in range(months):
        starts.append(
            now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        )
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return starts[::-1]


def monthly_spending(
    db: Session, household_id: uuid.UUID, months: int, tz: ZoneInfo, now: datetime | None = None
) -> list[MonthSpending]:
    local_now = (now or datetime.now(UTC)).astimezone(tz)
    starts = _month_starts(local_now, months)
    keys = [start.strftime("%Y-%m") for start in starts]

    purchases = db.scalars(
        select(ShoppingList).where(
            ShoppingList.household_id == household_id,
            ShoppingList.status == ShoppingListStatus.ARCHIVED,
            ShoppingList.completed_at >= starts[0],
        )
    ).all()
    item_totals: dict[uuid.UUID, int] = defaultdict(int)
    if purchases:
        rows = db.execute(
            select(
                ShoppingListItem.shopping_list_id,
                ShoppingListItem.quantity_bought,
                ShoppingListItem.unit_price_cents,
            ).where(
                ShoppingListItem.shopping_list_id.in_([purchase.id for purchase in purchases]),
                ShoppingListItem.status == ShoppingListItemStatus.CHECKED,
            )
        ).all()
        for list_id, quantity, price in rows:
            item_totals[list_id] += line_total_cents(quantity, price) or 0

    paid = dict.fromkeys(keys, 0)
    count = dict.fromkeys(keys, 0)
    for purchase in purchases:
        key = purchase.completed_at.astimezone(tz).strftime("%Y-%m")
        if key not in paid:
            continue
        total = purchase.receipt_total_cents
        paid[key] += total if total is not None else item_totals[purchase.id]
        count[key] += 1
    return [MonthSpending(month=key, paid_cents=paid[key], purchases=count[key]) for key in keys]


def recent_consumption(
    db: Session, household_id: uuid.UUID, days: int, now: datetime | None = None
) -> ConsumptionSummary:
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows = db.execute(
        select(
            Product.id,
            Product.name,
            Product.unit,
            func.sum(ConsumptionEvent.quantity),
            func.count(ConsumptionEvent.id),
        )
        .join(ConsumptionEvent, ConsumptionEvent.product_id == Product.id)
        .where(Product.household_id == household_id, ConsumptionEvent.consumed_at >= since)
        .group_by(Product.id, Product.name, Product.unit)
        .order_by(func.count(ConsumptionEvent.id).desc(), Product.name)
    ).all()
    products = [
        ProductUse(product_id=pid, name=name, unit=unit, quantity=Decimal(quantity), times=times)
        for pid, name, unit, quantity, times in rows
    ]
    return ConsumptionSummary(
        days=days, times=sum(product.times for product in products), products=products
    )


def price_history(db: Session, product: Product, limit: int) -> list[PricePoint]:
    rows = db.execute(
        select(
            ShoppingList.id,
            ShoppingList.completed_at,
            Market.name,
            ShoppingListItem.unit_price_cents,
        )
        .join(ShoppingListItem, ShoppingListItem.shopping_list_id == ShoppingList.id)
        .outerjoin(Market, Market.id == ShoppingList.market_id)
        .where(
            ShoppingListItem.product_id == product.id,
            ShoppingList.status == ShoppingListStatus.ARCHIVED,
            ShoppingListItem.unit_price_cents.is_not(None),
        )
        .order_by(ShoppingList.completed_at.desc())
        .limit(limit)
    ).all()
    return [
        PricePoint(purchase_id=pid, purchased_at=when, market_name=market, unit_price_cents=price)
        for pid, when, market, price in reversed(rows)
    ]
