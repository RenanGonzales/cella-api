"""minimum stock on products

Revision ID: 5a4ed3d47a10
Revises: eb459f002aab
Create Date: 2026-10-12 18:53:45.552342

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a4ed3d47a10"
down_revision: str | Sequence[str] | None = "eb459f002aab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing products keep their behavior: minimum = ideal (restock as soon as below ideal).
    op.add_column("products", sa.Column("min_quantity", sa.Numeric(10, 3), nullable=True))
    op.execute("UPDATE products SET min_quantity = ideal_quantity")
    op.alter_column("products", "min_quantity", nullable=False)
    op.create_check_constraint(
        op.f("ck_products_min_quantity_range"),
        "products",
        "min_quantity >= 0 AND min_quantity <= ideal_quantity",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_products_min_quantity_range"), "products", type_="check")
    op.drop_column("products", "min_quantity")
