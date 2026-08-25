"""A stand-in database, so the suite doesn't need the real DuckDB file.

redsox_25.duckdb is gitignored -- a clean checkout has no copy of it, and three
tests read the schedule for real. This builds a small one per test and points
server.DB_PATH at it, which also stops the write-path tests from writing into
the real database.

Tests that want a *different* database (missing file, empty file) monkeypatch
DB_PATH themselves; that runs after this fixture, so it wins.

Needs docker-compose Postgres running + `alembic upgrade head` against
tenth_inning_test (watch_history) -- a separate database, not the dev one,
same reason as the DuckDB file above: this suite truncates it.
"""

import os

os.environ["DATABASE_URL"] = (
    "postgresql://tenth_inning:tenth_inning@127.0.0.1:5433/tenth_inning_test"
)

import duckdb
import pytest
from sqlalchemy import text

import server

# Captured once, before any test can monkeypatch server.pg_engine -- so this
# fixture's teardown still hits the real database even if the test faked it.
REAL_PG_ENGINE = server.pg_engine

# Three games across two months, one already watched: enough for the schedule
# route's watch-state merge, a write that hits one existing and one new
# gamePk, and every /api/games filter (month, result, watched, paging).
#   gamePk, gameDate, officialDate, doubleheader, home_score, away_score, sox_won
SCHEDULE_ROWS = [
    (777, "2025-03-27 20:05:00", "2025-03-27", False, 5, 3, True),
    (778, "2025-03-29 17:10:00", "2025-03-29", True, 2, 6, False),
    (779, "2025-04-02 18:35:00", "2025-04-02", False, 7, 1, True),
]

# gamePk 779 deliberately has no innings, so "game exists, nothing recorded"
# stays distinguishable from "no such game".
LINESCORE_ROWS = [
    (777, 1, "1st", 2, 3, 0, 1, 0, 1, 0, 2),
    (777, 2, "2nd", 3, 4, 1, 2, 3, 3, 0, 1),
    (778, 1, "1st", 0, 1, 0, 3, 1, 2, 0, 0),
]


@pytest.fixture(autouse=True)
def fixture_db(tmp_path, monkeypatch):
    path = tmp_path / "fixture.duckdb"

    conn = duckdb.connect(str(path))
    try:
        conn.execute("""
            CREATE TABLE "2025_schedule" (
                gamePk BIGINT,
                gameDate TIMESTAMP,
                officialDate DATE,
                doubleheader BOOLEAN,
                home_score INTEGER,
                away_score INTEGER,
                sox_is_winner BOOLEAN
            )
        """)
        conn.executemany(
            'INSERT INTO "2025_schedule" VALUES (?, ?, ?, ?, ?, ?, ?)', SCHEDULE_ROWS
        )

        # Only the columns /api/games/{gamePk} actually reads back.
        conn.execute("""
            CREATE TABLE "2025_game_info" (
                gamePk BIGINT,
                officialDate DATE,
                home_team_name VARCHAR,
                away_team_name VARCHAR,
                home_score INTEGER,
                away_score INTEGER
            )
        """)
        conn.executemany(
            'INSERT INTO "2025_game_info" VALUES (?, ?, ?, ?, ?, ?)',
            [
                (777, "2025-03-27", "Boston Red Sox", "Texas Rangers", 5, 3),
                (778, "2025-03-29", "Boston Red Sox", "Texas Rangers", 2, 6),
                (779, "2025-04-02", "New York Yankees", "Boston Red Sox", 7, 1),
            ],
        )

        conn.execute("""
            CREATE TABLE "line_score_innings" (
                gamePk BIGINT, inning_num INTEGER, ordinalNum VARCHAR,
                home_runs INTEGER, home_hits INTEGER, home_errors INTEGER,
                home_leftOnBase INTEGER, away_runs INTEGER, away_hits INTEGER,
                away_errors INTEGER, away_leftOnBase INTEGER
            )
        """)
        conn.executemany(
            'INSERT INTO "line_score_innings" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            LINESCORE_ROWS,
        )
    finally:
        conn.close()

    monkeypatch.setattr(server, "DB_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def fixture_watch_history():
    """Postgres's watch_history, reset to one seed row (777, TRUE) per test."""
    with REAL_PG_ENGINE.begin() as conn:
        conn.execute(text("TRUNCATE TABLE watch_history"))
        conn.execute(
            text('INSERT INTO watch_history ("gamePk", watched) VALUES (777, TRUE)')
        )
    yield
    with REAL_PG_ENGINE.begin() as conn:
        conn.execute(text("TRUNCATE TABLE watch_history"))
