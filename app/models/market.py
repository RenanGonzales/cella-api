import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, enum_check, str_enum
from app.models.enums import CorridorKind, RouteStyle

# Largest floor plan, in grid cells (a big wholesale store fits in 40 x 30).
MAX_PLAN_COLS = 40
MAX_PLAN_ROWS = 30
MIN_PLAN_SIZE = 4


class Market(UUIDPrimaryKey, CreatedAt, Base):
    """A store as one household knows it: its name plus the household's corridor layout.

    The layout is personal because it maps the household's own categories. `chain` and
    `address` identify the physical store, so layouts can later be shared between
    households of the same store (see docs/data-model.md, "Shared markets").
    """

    __tablename__ = "markets"
    __table_args__ = (
        enum_check("route_style", RouteStyle),
        # A floor plan has both dimensions or none (a plain list of corridors).
        CheckConstraint(
            "(plan_cols IS NULL AND plan_rows IS NULL) OR "
            f"(plan_cols BETWEEN {MIN_PLAN_SIZE} AND {MAX_PLAN_COLS} "
            f"AND plan_rows BETWEEN {MIN_PLAN_SIZE} AND {MAX_PLAN_ROWS})",
            name="plan_size",
        ),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    chain: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    # Archived markets keep their purchase history but leave the market picker.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Floor plan grid, in cells; null when the market is only a list of corridors.
    plan_cols: Mapped[int | None] = mapped_column(Integer)
    plan_rows: Mapped[int | None] = mapped_column(Integer)
    route_style: Mapped[RouteStyle] = mapped_column(
        str_enum(RouteStyle), default=RouteStyle.COLUMN, server_default=RouteStyle.COLUMN.value
    )

    corridors: Mapped[list["Corridor"]] = relationship(
        back_populates="market", order_by="Corridor.position"
    )


class Corridor(UUIDPrimaryKey, Base):
    __tablename__ = "corridors"
    __table_args__ = (
        enum_check("kind", CorridorKind),
        # Placed on the plan (all four set, inside the grid's first quadrant) or not at all.
        CheckConstraint(
            "(x IS NULL AND y IS NULL AND w IS NULL AND h IS NULL) OR "
            "(x >= 0 AND y >= 0 AND w >= 1 AND h >= 1)",
            name="geometry",
        ),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    # Walking order inside the store; the shopping list is sorted by this.
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[CorridorKind] = mapped_column(
        str_enum(CorridorKind), default=CorridorKind.AISLE, server_default=CorridorKind.AISLE.value
    )
    # Place on the floor plan, in grid cells.
    x: Mapped[int | None] = mapped_column(Integer)
    y: Mapped[int | None] = mapped_column(Integer)
    w: Mapped[int | None] = mapped_column(Integer)
    h: Mapped[int | None] = mapped_column(Integer)

    market: Mapped[Market] = relationship(back_populates="corridors")


class CorridorCategory(UUIDPrimaryKey, Base):
    """Maps a category to the corridor where it is found in a given market."""

    __tablename__ = "corridor_categories"
    __table_args__ = (
        # A category lives in exactly one corridor per market.
        UniqueConstraint("market_id", "category_id"),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"))
    corridor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridors.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
