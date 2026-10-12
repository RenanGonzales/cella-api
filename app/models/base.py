import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names, so Alembic migrations stay stable and readable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Quantities keep three decimals (e.g. 0.250 kg); money is stored as integer cents.
Quantity = Numeric(10, 3)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    """Random UUID primary key, so public demo ids cannot be guessed."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def str_enum(enum_cls: type[PyEnum]) -> Enum:
    """Store a Python enum as plain text (no native PG enum: easier to migrate).

    Pair it with enum_check() so the database still rejects unknown values.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda members: [member.value for member in members],
    )


def enum_check(column: str, enum_cls: type[PyEnum]) -> CheckConstraint:
    """CHECK constraint that limits a text column to the values of an enum."""
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")
