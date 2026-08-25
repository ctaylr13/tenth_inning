"""contract: validate and promote status to not null

Revision ID: 82bb268a459f
Revises: 0dd5cd7b21fa
Create Date: 2026-08-25 16:47:52.304268

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "82bb268a459f"
down_revision: str | Sequence[str] | None = "0dd5cd7b21fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "migration_exercise_status_not_null"


def upgrade() -> None:
    op.execute("UPDATE migration_exercise SET status = 'pending' WHERE status IS NULL")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "migration_exercise",
        "status IS NOT NULL",
        postgresql_not_valid=True,
    )
    op.execute(f"ALTER TABLE migration_exercise VALIDATE CONSTRAINT {CONSTRAINT_NAME}")

    op.execute("ALTER TABLE migration_exercise ALTER COLUMN status SET NOT NULL")

    op.drop_constraint(CONSTRAINT_NAME, "migration_exercise", type_="check")


def downgrade() -> None:
    op.execute("ALTER TABLE migration_exercise ALTER COLUMN status DROP NOT NULL")
