import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Quantity, UUIDPrimaryKey


class ConsumptionEvent(UUIDPrimaryKey, Base):
    """One row per consume action; feeds the future stock autonomy forecast."""

    __tablename__ = "consumption_events"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
