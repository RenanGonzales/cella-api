import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models import ProductUnit, ShoppingListItemStatus, ShoppingListStatus
from app.schemas.catalog import JsonDecimal, NonNegativeQuantity, PositiveQuantity, ProductOut

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
    """Send only what changes.

    - `quantity_needed`: how much to buy (at home or in the store).
    - `status`: `checked` (in the cart), `not_found` or back to `pending`. Store only.
    - `quantity_bought`: for checked items; defaults to `quantity_needed`. Store only.
    - `assigned_user_id`: who picks it up; null to unassign. Store only.
    """

    quantity_needed: PositiveQuantity | None = None
    status: ShoppingListItemStatus | None = None
    quantity_bought: NonNegativeQuantity | None = None
    assigned_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def valid_changes(self) -> "ShoppingListItemUpdate":
        if not self.model_fields_set:
            raise ValueError("Send at least one field")
        for field in self.model_fields_set - {"assigned_user_id"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class StartShoppingRequest(BaseModel):
    market_id: uuid.UUID


class SplitRequest(BaseModel):
    """Household members going to the market, in the order they take the corridors."""

    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class CheckoutResponse(BaseModel):
    purchase_id: uuid.UUID = Field(description="The archived list, now in /purchases")
    items_bought: int
    items_carried_over: int = Field(description="Not found or pending: moved to a new list")
    total_cents: int = Field(description="Sum of the items that already have a price")
    items_without_price: int


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


# --- Purchases (archived lists) -------------------------------------------


class PurchaseSummary(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID | None
    market_name: str | None
    started_at: datetime | None
    completed_at: datetime
    items_bought: int
    items_without_price: int
    total_cents: int = Field(description="Sum of quantity x unit price of priced items")


class PurchaseItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    brand: str | None
    unit: ProductUnit
    status: ShoppingListItemStatus
    quantity_bought: JsonDecimal | None
    unit_price_cents: int | None
    line_total_cents: int | None


class PurchaseDetail(PurchaseSummary):
    items: list[PurchaseItemOut]


class PurchaseItemUpdate(BaseModel):
    """Price per product unit (per kg, per liter...). Null removes it."""

    unit_price_cents: int | None = Field(ge=0, le=100_000_000)
