import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import ProductUnit
from app.schemas.catalog import JsonDecimal


class MonthSpending(BaseModel):
    month: str = Field(description="YYYY-MM, in the requested time zone")
    paid_cents: int = Field(description="Receipt totals, or the sum of priced items")
    purchases: int


class ProductUse(BaseModel):
    product_id: uuid.UUID
    name: str
    unit: ProductUnit
    quantity: JsonDecimal
    times: int


class ConsumptionSummary(BaseModel):
    days: int
    times: int = Field(description="Number of 'Use' taps in the period")
    products: list[ProductUse]


class PricePoint(BaseModel):
    purchase_id: uuid.UUID
    purchased_at: datetime
    market_name: str | None
    unit_price_cents: int
