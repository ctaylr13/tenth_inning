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

# Two games, one of them already watched: enough for the schedule route's
# LEFT JOIN branch, and for a write that hits one existing and one new gamePk.
SCHEDULE_ROWS = [
    (777, "2025-03-27 20:05:00", "2025-03-27", False),
    (778, "2025-03-29 17:10:00", "2025-03-29", True),
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
                doubleheader BOOLEAN
            )
        """)
        conn.executemany(
            'INSERT INTO "2025_schedule" VALUES (?, ?, ?, ?)', SCHEDULE_ROWS
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
