import uuid

import pytest
from conftest import REAL_PG_ENGINE
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_phase_3_foundation_tables_exist():
    with REAL_PG_ENGINE.connect() as conn:
        names = set(
            conn.execute(
                text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'team', 'team_season', 'game', 'team_season_game', 'artifact'
                  )
                """)
            ).scalars()
        )

    assert names == {
        "team",
        "team_season",
        "game",
        "team_season_game",
        "artifact",
    }


def test_migration_boundary_columns_are_nullable():
    with REAL_PG_ENGINE.connect() as conn:
        rows = conn.execute(
            text("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'game'
              AND column_name IN (
                  'game_time_utc', 'coded_game_state', 'detailed_state',
                  'rescheduled_from', 'away_score', 'home_score'
              )
            """)
        )
        nullable = {row.column_name: row.is_nullable for row in rows}

    assert nullable == {
        "game_time_utc": "YES",
        "coded_game_state": "YES",
        "detailed_state": "YES",
        "rescheduled_from": "YES",
        "away_score": "YES",
        "home_score": "YES",
    }


def test_artifact_requires_exactly_one_subject_shape():
    with REAL_PG_ENGINE.connect() as conn:
        transaction = conn.begin()
        try:
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(
                    text("""
                        INSERT INTO artifact (
                            id, kind, game_pk, team_id, season, schema_version
                        )
                        VALUES (
                            :id, 'game', NULL, NULL, NULL, 1
                        )
                    """),
                    {"id": uuid.uuid4()},
                )
        finally:
            transaction.rollback()


def test_artifact_version_is_unique_per_game():
    with REAL_PG_ENGINE.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(
                text("""
                    INSERT INTO team (team_id, name, abbreviation)
                    VALUES (99111, 'Away Test', 'AWY'), (99116, 'Home Test', 'HME')
                """),
            )
            conn.execute(
                text("""
                    INSERT INTO game (
                        game_pk, official_date, is_doubleheader, game_number,
                        away_team_id, home_team_id
                    )
                    VALUES (99777940, DATE '2025-05-13', FALSE, 1, 99111, 99116)
                """),
            )
            conn.execute(
                text("""
                    INSERT INTO artifact (id, kind, game_pk, schema_version)
                    VALUES (:id, 'game', 99777940, 1)
                """),
                {"id": uuid.uuid4()},
            )

            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(
                    text("""
                        INSERT INTO artifact (id, kind, game_pk, schema_version)
                        VALUES (:id, 'game', 99777940, 1)
                    """),
                    {"id": uuid.uuid4()},
                )
        finally:
            transaction.rollback()
