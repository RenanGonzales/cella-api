"""demo sandbox expiry

Revision ID: 3e8fd442e752
Revises: 5a4ed3d47a10
Create Date: 2026-10-12 20:47:13.411452

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e8fd442e752"
down_revision: str | Sequence[str] | None = "5a4ed3d47a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null for every existing household: only per-visitor demo copies expire.
    op.add_column(
        "households", sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_households_demo_expires_at"), "households", ["demo_expires_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_households_demo_expires_at"), table_name="households")
    op.drop_column("households", "demo_expires_at")
