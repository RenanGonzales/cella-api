"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.base import Base
from app.models.catalog import Category, Product, StorageArea
from app.models.consumption import ConsumptionEvent
from app.models.enums import (
    CorridorKind,
    ProductUnit,
    ReceiptSource,
    RouteStyle,
    ShoppingListItemStatus,
    ShoppingListStatus,
)
from app.models.household import Household
from app.models.market import Corridor, CorridorCategory, Market
from app.models.shopping import ShoppingList, ShoppingListItem
from app.models.user import User

__all__ = [
    "Base",
    "Category",
    "ConsumptionEvent",
    "Corridor",
    "CorridorCategory",
    "CorridorKind",
    "Household",
    "Market",
    "Product",
    "ProductUnit",
    "ReceiptSource",
    "RouteStyle",
    "ShoppingList",
    "ShoppingListItem",
    "ShoppingListItemStatus",
    "ShoppingListStatus",
    "StorageArea",
    "User",
]
