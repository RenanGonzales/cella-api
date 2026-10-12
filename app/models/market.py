import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey


class Market(UUIDPrimaryKey, Base):
    __tablename__ = "markets"

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))

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
