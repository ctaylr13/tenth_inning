"""expand: add status column nullable

Revision ID: 0dd5cd7b21fa
Revises: f2a2dcb8094b
Create Date: 2026-08-25 16:47:52.132179

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0dd5cd7b21fa"
down_revision: str | Sequence[str] | None = "f2a2dcb8094b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("migration_exercise", sa.Column("status", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("migration_exercise", "status")
