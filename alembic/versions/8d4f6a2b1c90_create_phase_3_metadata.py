"""create Phase 3 metadata foundation

Revision ID: 8d4f6a2b1c90
Revises: 1a83830409d0
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8d4f6a2b1c90"
down_revision: str | Sequence[str] | None = "1a83830409d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team",
        sa.Column("team_id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("abbreviation", sa.String(3), nullable=False),
        sa.CheckConstraint("team_id > 0", name="team_id_positive"),
    )

    op.create_table(
        "team_season",
        sa.Column("team_id", sa.BigInteger, nullable=False),
        sa.Column("season", sa.SmallInteger, nullable=False),
        sa.Column("ingest_status", sa.String(16), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["team.team_id"]),
        sa.PrimaryKeyConstraint("team_id", "season"),
        sa.CheckConstraint("season > 0", name="team_season_year_positive"),
        sa.CheckConstraint(
            "ingest_status IN ('cold', 'ingesting', 'ready')",
            name="team_season_ingest_status_valid",
        ),
    )

    op.create_table(
        "game",
        sa.Column("game_pk", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("official_date", sa.Date, nullable=False),
        sa.Column("game_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coded_game_state", sa.String(8), nullable=True),
        sa.Column("detailed_state", sa.Text, nullable=True),
        sa.Column("is_doubleheader", sa.Boolean, nullable=False),
        sa.Column("game_number", sa.SmallInteger, nullable=False),
        sa.Column("rescheduled_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("away_team_id", sa.BigInteger, nullable=False),
        sa.Column("home_team_id", sa.BigInteger, nullable=False),
        sa.Column("away_score", sa.SmallInteger, nullable=True),
        sa.Column("home_score", sa.SmallInteger, nullable=True),
        sa.ForeignKeyConstraint(["away_team_id"], ["team.team_id"]),
        sa.ForeignKeyConstraint(["home_team_id"], ["team.team_id"]),
        sa.CheckConstraint("game_pk > 0", name="game_pk_positive"),
        sa.CheckConstraint("game_number > 0", name="game_number_positive"),
        sa.CheckConstraint("away_team_id <> home_team_id", name="game_teams_differ"),
        sa.CheckConstraint("away_score >= 0", name="away_score_nonnegative"),
        sa.CheckConstraint("home_score >= 0", name="home_score_nonnegative"),
    )
    op.create_index(
        "game_official_order",
        "game",
        ["official_date", "game_number", "game_pk"],
    )

    op.create_table(
        "team_season_game",
        sa.Column("team_id", sa.BigInteger, nullable=False),
        sa.Column("season", sa.SmallInteger, nullable=False),
        sa.Column("game_pk", sa.BigInteger, nullable=False),
        sa.Column("did_win", sa.Boolean, nullable=True),
        sa.Column("cumulative_wins", sa.SmallInteger, nullable=True),
        sa.Column("cumulative_losses", sa.SmallInteger, nullable=True),
        sa.Column("standings_position", sa.SmallInteger, nullable=True),
        sa.ForeignKeyConstraint(
            ["team_id", "season"],
            ["team_season.team_id", "team_season.season"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["game_pk"], ["game.game_pk"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "season", "game_pk"),
        sa.CheckConstraint(
            "cumulative_wins >= 0", name="team_season_game_wins_nonnegative"
        ),
        sa.CheckConstraint(
            "cumulative_losses >= 0", name="team_season_game_losses_nonnegative"
        ),
        sa.CheckConstraint(
            "standings_position > 0", name="team_season_game_position_positive"
        ),
    )

    op.create_table(
        "artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("game_pk", sa.BigInteger, nullable=True),
        sa.Column("team_id", sa.BigInteger, nullable=True),
        sa.Column("season", sa.SmallInteger, nullable=True),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("byte_size", sa.BigInteger, nullable=True),
        sa.Column("gcs_key", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["game_pk"], ["game.game_pk"]),
        sa.ForeignKeyConstraint(
            ["team_id", "season"],
            ["team_season.team_id", "team_season.season"],
        ),
        sa.CheckConstraint(
            "(kind = 'game' AND game_pk IS NOT NULL "
            "AND team_id IS NULL AND season IS NULL) OR "
            "(kind = 'season_manifest' AND game_pk IS NULL "
            "AND team_id IS NOT NULL AND season IS NOT NULL)",
            name="artifact_subject_matches_kind",
        ),
        sa.CheckConstraint(
            "schema_version > 0", name="artifact_schema_version_positive"
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="artifact_checksum_sha256_valid",
        ),
        sa.CheckConstraint("byte_size > 0", name="artifact_byte_size_positive"),
    )
    op.create_index(
        "one_game_artifact_version",
        "artifact",
        ["game_pk", "schema_version"],
        unique=True,
        postgresql_where=sa.text("kind = 'game'"),
    )
    op.create_index(
        "one_manifest_artifact_version",
        "artifact",
        ["team_id", "season", "schema_version"],
        unique=True,
        postgresql_where=sa.text("kind = 'season_manifest'"),
    )


def downgrade() -> None:
    op.drop_table("artifact")
    op.drop_table("team_season_game")
    op.drop_index("game_official_order", table_name="game")
    op.drop_table("game")
    op.drop_table("team_season")
    op.drop_table("team")
