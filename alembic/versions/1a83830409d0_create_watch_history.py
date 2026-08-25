"""create watch_history

Revision ID: 1a83830409d0
Revises:
Create Date: 2026-08-25 15:52:43.559368

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a83830409d0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watch_history",
        # autoincrement=False -- gamePk is MLB's id, not a surrogate key.
        sa.Column("gamePk", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("watched", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("watch_history")
