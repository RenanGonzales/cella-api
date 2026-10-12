import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, field_validator, model_validator

from app.models import ProductUnit

# Quantities are exact decimals in the database, sent as plain JSON numbers (1.5, not "1.500").
JsonDecimal = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

Name = Annotated[str, Field(min_length=1, max_length=50)]


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


# --- Storage areas --------------------------------------------------------


class StorageAreaCreate(BaseModel):
    name: Name

    _strip = field_validator("name", mode="before")(_strip)


class StorageAreaUpdate(BaseModel):
    name: Name | None = None

    _strip = field_validator("name", mode="before")(_strip)


class StorageAreaOrder(BaseModel):
    """All of the household's storage area ids, in the new order."""

    ids: list[uuid.UUID] = Field(min_length=1)


class StorageAreaOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int


# --- Categories -----------------------------------------------------------


class CategoryCreate(BaseModel):
    name: Name

    _strip = field_validator("name", mode="before")(_strip)


class CategoryUpdate(BaseModel):
    name: Name | None = None

    _strip = field_validator("name", mode="before")(_strip)


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str


# --- Products -------------------------------------------------------------

PositiveQuantity = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
NonNegativeQuantity = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]


class ProductCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    brand: Annotated[str | None, Field(max_length=100)] = None
    category_id: uuid.UUID
    storage_area_id: uuid.UUID
    unit: ProductUnit
    consume_step: PositiveQuantity
    ideal_quantity: NonNegativeQuantity
    current_quantity: NonNegativeQuantity = Decimal("0")

    _strip = field_validator("name", "brand", mode="before")(_strip)


class ProductUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    brand: Annotated[str | None, Field(max_length=100)] = None
    category_id: uuid.UUID | None = None
    storage_area_id: uuid.UUID | None = None
    unit: ProductUnit | None = None
    consume_step: PositiveQuantity | None = None
    ideal_quantity: NonNegativeQuantity | None = None
    current_quantity: NonNegativeQuantity | None = None

    _strip = field_validator("name", "brand", mode="before")(_strip)

    @model_validator(mode="after")
    def only_brand_can_be_cleared(self) -> "ProductUpdate":
        """Omitted fields stay as they are; only `brand` accepts null (to remove it)."""
        for field in self.model_fields_set - {"brand"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category_id: uuid.UUID
    storage_area_id: uuid.UUID
    unit: ProductUnit
    consume_step: JsonDecimal
    ideal_quantity: JsonDecimal
    current_quantity: JsonDecimal
    below_ideal: bool
    last_price_cents: int | None = Field(description="Price per unit in the last purchase")
    last_purchased_at: datetime | None
    archived_at: datetime | None
