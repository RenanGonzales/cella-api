import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Quantity, UUIDPrimaryKey, enum_check, str_enum
from app.models.enums import ReceiptSource, ShoppingListItemStatus, ShoppingListStatus


class ShoppingList(UUIDPrimaryKey, Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (
        # At most one active (open or shopping) list per household.
        Index(
            "uq_shopping_lists_one_active_per_household",
            "household_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'shopping')"),
        ),
        enum_check("status", ShoppingListStatus),
        enum_check("receipt_source", ReceiptSource),
        CheckConstraint("receipt_total_cents >= 0", name="receipt_total_positive"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Chosen when shopping starts; archived lists keep it for price analytics.
    market_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("markets.id"), index=True)
    status: Mapped[ShoppingListStatus] = mapped_column(
        str_enum(ShoppingListStatus),
        default=ShoppingListStatus.OPEN,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # Set when the receipt of an archived list is confirmed.
    receipt_source: Mapped[ReceiptSource | None] = mapped_column(str_enum(ReceiptSource))
    receipt_total_cents: Mapped[int | None] = mapped_column(Integer)

    items: Mapped[list["ShoppingListItem"]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan"
    )


class ShoppingListItem(UUIDPrimaryKey, Base):
    __tablename__ = "shopping_list_items"
    __table_args__ = (
        UniqueConstraint("shopping_list_id", "product_id"),
        CheckConstraint("quantity_needed > 0", name="quantity_needed_positive"),
        CheckConstraint("quantity_bought >= 0", name="quantity_bought_non_negative"),
        CheckConstraint("unit_price_cents >= 0", name="unit_price_cents_non_negative"),
        enum_check("status", ShoppingListItemStatus),
    )

    shopping_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    quantity_needed: Mapped[Decimal] = mapped_column(Quantity)
    quantity_bought: Mapped[Decimal | None] = mapped_column(Quantity)
    # Price per product unit (per kg, per liter...), filled in later at home.
    unit_price_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ShoppingListItemStatus] = mapped_column(
        str_enum(ShoppingListItemStatus),
        default=ShoppingListItemStatus.PENDING,
    )
    # True once a person added the item or changed its quantity: automatic updates
    # (consume, undo) then never shrink or remove it.
    added_manually: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Household member responsible for this item when the list is split.
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")
