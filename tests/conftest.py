"""A stand-in database, so the suite doesn't need the real DuckDB file.

redsox_25.duckdb is gitignored -- a clean checkout has no copy of it, and three
tests read the schedule for real. This builds a small one per test and points
server.DB_PATH at it, which also stops the write-path tests from writing into
the real database.

Tests that want a *different* database (missing file, empty file) monkeypatch
DB_PATH themselves; that runs after this fixture, so it wins.
"""

import duckdb
import pytest

import server

# Three games across two months, one already watched: enough for the schedule
# route's LEFT JOIN branch, a write that hits one existing and one new gamePk,
# and every /api/games filter (month, result, watched, paging).
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
        conn.execute("""
            CREATE TABLE "watch_history" (
                gamePk BIGINT,
                watched BOOLEAN DEFAULT FALSE
            )
        """)
        conn.execute('INSERT INTO "watch_history" VALUES (777, TRUE)')
    finally:
        conn.close()

    monkeypatch.setattr(server, "DB_PATH", str(path))
    return path
