from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User


class Household(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "households"

    name: Mapped[str] = mapped_column(String(100))
    # Code shared with other members so they can join this household.
    invite_code: Mapped[str] = mapped_column(String(12), unique=True)
    # Set only on demo sandboxes (one per visitor): when they are deleted. Null = real household.
    demo_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=None
    )

    users: Mapped[list["User"]] = relationship(back_populates="household")
