import uuid

from pydantic import BaseModel, Field

from app.models import ProductUnit, ShoppingListItemStatus, ShoppingListStatus
from app.schemas.catalog import JsonDecimal, PositiveQuantity, ProductOut

# --- Consumption ----------------------------------------------------------


class ConsumeRequest(BaseModel):
    """Optional body. Without it, one `consume_step` of the product is consumed."""

    quantity: PositiveQuantity | None = None


class ConsumeResponse(BaseModel):
    product: ProductOut
    consumption_event_id: uuid.UUID | None = Field(
        description="Id to undo this consumption; null when the stock was already at zero"
    )
    consumed: JsonDecimal = Field(description="Amount actually removed from stock")
    added_to_list: bool = Field(description="True when the product is now on the shopping list")


class UndoResponse(BaseModel):
    product: ProductOut
    restored: JsonDecimal


# --- Shopping list --------------------------------------------------------


class ShoppingListItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity_needed: PositiveQuantity


class ShoppingListItemUpdate(BaseModel):
    quantity_needed: PositiveQuantity


class ShoppingListItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    brand: str | None
    category: str
    unit: ProductUnit
    quantity_needed: JsonDecimal
    quantity_bought: JsonDecimal | None
    status: ShoppingListItemStatus
    added_manually: bool
    assigned_user_id: uuid.UUID | None
    last_price_cents: int | None = Field(description="Price per unit in the last purchase")


class ShoppingListGroup(BaseModel):
    """Items of one corridor (when sorted by a market) or one category (otherwise)."""

    corridor_id: uuid.UUID | None = Field(description='Null for the "Other" group')
    name: str
    items: list[ShoppingListItemOut]


class ShoppingListOut(BaseModel):
    id: uuid.UUID | None = Field(description="Null when the household has no active list yet")
    status: ShoppingListStatus | None
    market_id: uuid.UUID | None = Field(description="Market chosen when shopping started")
    sorted_by_market_id: uuid.UUID | None = Field(description="Market used to group the items")
    item_count: int
    groups: list[ShoppingListGroup]
