import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.catalog import CategoryOut

MAX_CORRIDORS = 60


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: str | None) -> str | None:
    value = _strip(value)
    return value or None


# --- Markets --------------------------------------------------------------


class MarketCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    chain: Annotated[str | None, Field(max_length=100)] = None
    address: Annotated[str | None, Field(max_length=255)] = None

    _strip = field_validator("name", mode="before")(_strip)
    _optional = field_validator("chain", "address", mode="before")(_blank_to_none)


class MarketUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    chain: Annotated[str | None, Field(max_length=100)] = None
    address: Annotated[str | None, Field(max_length=255)] = None

    _strip = field_validator("name", mode="before")(_strip)
    _optional = field_validator("chain", "address", mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def name_cannot_be_cleared(self) -> "MarketUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class MarketOut(BaseModel):
    id: uuid.UUID
    name: str
    chain: str | None
    address: str | None
    corridor_count: int
    archived_at: datetime | None


# --- Layout ---------------------------------------------------------------


class LayoutCorridorIn(BaseModel):
    """One corridor of the layout. Send `id` to keep an existing corridor, omit it to create one."""

    id: uuid.UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=50)]
    category_ids: list[uuid.UUID] = []

    _strip = field_validator("name", mode="before")(_strip)


class LayoutIn(BaseModel):
    """The whole layout, corridors in walking order. Replaces the current layout atomically."""

    corridors: Annotated[list[LayoutCorridorIn], Field(max_length=MAX_CORRIDORS)]

    @model_validator(mode="after")
    def consistent(self) -> "LayoutIn":
        corridor_ids = [corridor.id for corridor in self.corridors if corridor.id is not None]
        if len(corridor_ids) != len(set(corridor_ids)):
            raise ValueError("A corridor id appears more than once")

        names = [corridor.name.lower() for corridor in self.corridors]
        if len(names) != len(set(names)):
            raise ValueError("Corridor names must be unique within a market")

        category_ids = [cid for corridor in self.corridors for cid in corridor.category_ids]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("A category can only be in one corridor per market")
        return self


class LayoutCorridorOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    categories: list[CategoryOut]


class LayoutOut(BaseModel):
    market_id: uuid.UUID
    corridors: list[LayoutCorridorOut]
    unmapped_categories: list[CategoryOut] = Field(
        description="Categories with no corridor here; the shopping list groups them as Other"
    )
