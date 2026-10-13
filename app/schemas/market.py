import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import CorridorKind, RouteStyle
from app.models.market import MAX_PLAN_COLS, MAX_PLAN_ROWS, MIN_PLAN_SIZE
from app.schemas.catalog import CategoryOut

MAX_CORRIDORS = 100
# Pieces that mark where the route starts and ends: one each, never with categories.
ROUTE_ENDS = (CorridorKind.ENTRANCE, CorridorKind.CHECKOUT)


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
    corridor_count: int = Field(description="Corridors with products (not entrance or checkout)")
    has_plan: bool = Field(description="True when the market has a floor plan")
    archived_at: datetime | None


# --- Layout ---------------------------------------------------------------


class LayoutCorridorIn(BaseModel):
    """One corridor of the layout. Send `id` to keep an existing corridor, omit it to create one."""

    id: uuid.UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=50)]
    category_ids: list[uuid.UUID] = []
    kind: CorridorKind = CorridorKind.AISLE
    # Place on the floor plan, in cells. All four with a plan, none without.
    x: Annotated[int | None, Field(ge=0, lt=MAX_PLAN_COLS)] = None
    y: Annotated[int | None, Field(ge=0, lt=MAX_PLAN_ROWS)] = None
    w: Annotated[int | None, Field(ge=1, le=MAX_PLAN_COLS)] = None
    h: Annotated[int | None, Field(ge=1, le=MAX_PLAN_ROWS)] = None

    _strip = field_validator("name", mode="before")(_strip)

    @property
    def placed(self) -> bool:
        return None not in (self.x, self.y, self.w, self.h)

    @property
    def unplaced(self) -> bool:
        return (self.x, self.y, self.w, self.h) == (None, None, None, None)

    def overlaps(self, other: "LayoutCorridorIn") -> bool:
        return (
            self.x < other.x + other.w  # type: ignore[operator]
            and other.x < self.x + self.w  # type: ignore[operator]
            and self.y < other.y + other.h  # type: ignore[operator]
            and other.y < self.y + self.h  # type: ignore[operator]
        )


class PlanSize(BaseModel):
    """The floor plan grid, in cells."""

    cols: Annotated[int, Field(ge=MIN_PLAN_SIZE, le=MAX_PLAN_COLS)]
    rows: Annotated[int, Field(ge=MIN_PLAN_SIZE, le=MAX_PLAN_ROWS)]


class LayoutIn(BaseModel):
    """The whole layout, corridors in walking order. Replaces the current layout atomically.

    With `plan`, every corridor is placed on the grid (x, y, w, h), inside it and without
    overlapping another one. Without it, the market is a plain list and nothing is placed.
    """

    corridors: Annotated[list[LayoutCorridorIn], Field(max_length=MAX_CORRIDORS)]
    plan: PlanSize | None = None
    route_style: RouteStyle = RouteStyle.COLUMN

    @model_validator(mode="after")
    def valid_plan(self) -> "LayoutIn":
        for kind in ROUTE_ENDS:
            ends = [corridor for corridor in self.corridors if corridor.kind == kind]
            if len(ends) > 1:
                raise ValueError(f"Only one {kind.value} per market")
            if any(corridor.category_ids for corridor in ends):
                raise ValueError(f"The {kind.value} cannot have categories")

        if self.plan is None:
            if not all(corridor.unplaced for corridor in self.corridors):
                raise ValueError("Send plan to place corridors on a floor plan")
            return self

        for corridor in self.corridors:
            if not corridor.placed:
                raise ValueError(f"{corridor.name}: x, y, w and h are required with a plan")
            if (
                corridor.x + corridor.w > self.plan.cols  # type: ignore[operator]
                or corridor.y + corridor.h > self.plan.rows  # type: ignore[operator]
            ):
                raise ValueError(f"{corridor.name} goes outside the plan")
        for index, corridor in enumerate(self.corridors):
            for other in self.corridors[index + 1 :]:
                if corridor.overlaps(other):
                    raise ValueError(f"{corridor.name} overlaps {other.name}")
        return self

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
    kind: CorridorKind
    x: int | None
    y: int | None
    w: int | None
    h: int | None
    categories: list[CategoryOut]


class LayoutOut(BaseModel):
    market_id: uuid.UUID
    plan: PlanSize | None = Field(description="Null when the market is a plain list")
    route_style: RouteStyle
    corridors: list[LayoutCorridorOut]
    unmapped_categories: list[CategoryOut] = Field(
        description="Categories with no corridor here; the shopping list groups them as Other"
    )
