"""Receipts: a draft read from a photo (or the demo's sample) and its confirmation."""

import uuid
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ReceiptSource
from app.schemas.catalog import JsonDecimal

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_RECEIPT_LINES = 200


class ReceiptLine(BaseModel):
    text: str = Field(description="The line as printed on the receipt")
    quantity: JsonDecimal | None
    unit_price_cents: int | None
    line_total_cents: int | None
    product_id: uuid.UUID | None = Field(description="Suggested product of the household")
    previous_price_cents: int | None = Field(description="Last price paid before this purchase")


class ReceiptDraft(BaseModel):
    """What was read from the receipt. Nothing is saved until it is confirmed."""

    source: ReceiptSource
    store_name: str | None
    purchased_on: date | None
    total_cents: int | None
    lines: list[ReceiptLine]


class ReceiptImage(BaseModel):
    """A photo of the receipt, base64 encoded. It is read and discarded, never stored."""

    media_type: str
    data: str = Field(max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)

    @field_validator("media_type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in IMAGE_TYPES:
            raise ValueError(f"media_type must be one of {', '.join(IMAGE_TYPES)}")
        return value


class ReceiptPrice(BaseModel):
    product_id: uuid.UUID
    unit_price_cents: int = Field(ge=0, le=100_000_000)


class ReceiptConfirm(BaseModel):
    """The reviewed receipt: the price of each product bought, and what was paid in total."""

    source: ReceiptSource
    total_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    prices: list[ReceiptPrice] = Field(max_length=MAX_RECEIPT_LINES)

    @field_validator("prices")
    @classmethod
    def one_price_per_product(cls, prices: list[ReceiptPrice]) -> list[ReceiptPrice]:
        ids = [price.product_id for price in prices]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product can have only one price")
        return prices
