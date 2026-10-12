import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey


class Market(UUIDPrimaryKey, CreatedAt, Base):
    """A store as one household knows it: its name plus the household's corridor layout.

    The layout is personal because it maps the household's own categories. `chain` and
    `address` identify the physical store, so layouts can later be shared between
    households of the same store (see docs/data-model.md, "Shared markets").
    """

    __tablename__ = "markets"

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    chain: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    # Archived markets keep their purchase history but leave the market picker.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    corridors: Mapped[list["Corridor"]] = relationship(
        back_populates="market", order_by="Corridor.position"
    )


class Corridor(UUIDPrimaryKey, Base):
    __tablename__ = "corridors"

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    # Walking order inside the store; the shopping list is sorted by this.
    position: Mapped[int] = mapped_column(Integer, default=0)

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
