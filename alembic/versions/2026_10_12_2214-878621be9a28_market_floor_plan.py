"""market floor plan

Revision ID: 878621be9a28
Revises: 3e8fd442e752
Create Date: 2026-10-12 22:14:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "878621be9a28"
down_revision: str | Sequence[str] | None = "3e8fd442e752"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing markets stay plain lists of corridors (no plan), walked column by column.
    op.add_column("markets", sa.Column("plan_cols", sa.Integer(), nullable=True))
    op.add_column("markets", sa.Column("plan_rows", sa.Integer(), nullable=True))
    op.add_column(
        "markets",
        sa.Column("route_style", sa.String(length=20), server_default="column", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_markets_route_style_valid"), "markets", "route_style IN ('column', 'block')"
    )
    op.create_check_constraint(
        op.f("ck_markets_plan_size"),
        "markets",
        "(plan_cols IS NULL AND plan_rows IS NULL) OR "
        "(plan_cols BETWEEN 4 AND 40 AND plan_rows BETWEEN 4 AND 30)",
    )

    # Existing corridors are aisles that are not placed on any plan yet.
    op.add_column(
        "corridors",
        sa.Column("kind", sa.String(length=20), server_default="aisle", nullable=False),
    )
    for column in ("x", "y", "w", "h"):
        op.add_column("corridors", sa.Column(column, sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_corridors_kind_valid"),
        "corridors",
        "kind IN ('aisle', 'wall', 'island', 'entrance', 'checkout')",
    )
    op.create_check_constraint(
        op.f("ck_corridors_geometry"),
        "corridors",
        "(x IS NULL AND y IS NULL AND w IS NULL AND h IS NULL) OR "
        "(x >= 0 AND y >= 0 AND w >= 1 AND h >= 1)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_corridors_geometry"), "corridors", type_="check")
    op.drop_constraint(op.f("ck_corridors_kind_valid"), "corridors", type_="check")
    for column in ("h", "w", "y", "x", "kind"):
        op.drop_column("corridors", column)
    op.drop_constraint(op.f("ck_markets_plan_size"), "markets", type_="check")
    op.drop_constraint(op.f("ck_markets_route_style_valid"), "markets", type_="check")
    for column in ("route_style", "plan_rows", "plan_cols"):
        op.drop_column("markets", column)
