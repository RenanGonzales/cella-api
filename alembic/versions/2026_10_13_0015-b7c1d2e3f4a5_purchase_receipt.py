"""purchase receipt

Revision ID: b7c1d2e3f4a5
Revises: 878621be9a28
Create Date: 2026-10-13 00:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "878621be9a28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Past purchases have no confirmed receipt: both columns start empty.
    op.add_column("shopping_lists", sa.Column("receipt_source", sa.String(20), nullable=True))
    op.add_column("shopping_lists", sa.Column("receipt_total_cents", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_shopping_lists_receipt_source_valid"),
        "shopping_lists",
        "receipt_source IN ('sample', 'ai', 'manual')",
    )
    op.create_check_constraint(
        op.f("ck_shopping_lists_receipt_total_positive"),
        "shopping_lists",
        "receipt_total_cents >= 0",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("ck_shopping_lists_receipt_total_positive"), "shopping_lists", type_="check"
    )
    op.drop_constraint(
        op.f("ck_shopping_lists_receipt_source_valid"), "shopping_lists", type_="check"
    )
    op.drop_column("shopping_lists", "receipt_total_cents")
    op.drop_column("shopping_lists", "receipt_source")
