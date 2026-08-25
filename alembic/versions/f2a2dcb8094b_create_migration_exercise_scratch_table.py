"""create migration_exercise scratch table

Revision ID: f2a2dcb8094b
Revises: 1a83830409d0
Create Date: 2026-08-25 16:47:51.952803

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a2dcb8094b"
down_revision: str | Sequence[str] | None = "1a83830409d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "migration_exercise",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "migration_exercise",
            sa.column("id", sa.BigInteger),
            sa.column("label", sa.Text),
        ),
        [{"id": i, "label": f"row-{i}"} for i in range(1, 6)],
    )


def downgrade() -> None:
    op.drop_table("migration_exercise")
