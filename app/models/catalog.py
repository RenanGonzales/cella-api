import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, Quantity, UUIDPrimaryKey, enum_check, str_enum
from app.models.enums import ProductUnit


class StorageArea(UUIDPrimaryKey, Base):
    """Where an item lives at home: fridge, pantry, bathroom, laundry..."""

    __tablename__ = "storage_areas"

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    # Order of the buttons on the home grid.
    position: Mapped[int] = mapped_column(Integer, default=0)


class Category(UUIDPrimaryKey, Base):
    """Product category; each market maps categories to its corridors."""

    __tablename__ = "categories"

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))


class Product(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("consume_step > 0", name="consume_step_positive"),
        CheckConstraint("ideal_quantity >= 0", name="ideal_quantity_non_negative"),
        CheckConstraint("current_quantity >= 0", name="current_quantity_non_negative"),
        enum_check("unit", ProductUnit),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), index=True)
    storage_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_areas.id"), index=True)

    name: Mapped[str] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[ProductUnit] = mapped_column(str_enum(ProductUnit))
    # Amount removed by one tap on "consume"; also the package size used for rounding.
    consume_step: Mapped[Decimal] = mapped_column(Quantity)
    ideal_quantity: Mapped[Decimal] = mapped_column(Quantity)
    current_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"))
    # Soft delete: archived products disappear from the UI but keep their history.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship()
    storage_area: Mapped[StorageArea] = relationship()
