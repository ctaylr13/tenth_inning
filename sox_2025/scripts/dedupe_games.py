"""One-time repair: collapse duplicate gamePk rows in the per-game tables.

The MLB schedule API lists a postponed game under both its original date block
and its makeup date block, under one gamePk. regular_season.py used to append
every entry, which put 167 rows in 2025_schedule for 162 games -- and every
per-game table built from that same loop inherited the same five duplicates.
It broke watch-history saves outright: the PUT payload repeated those gamePks,
and the API rejects a payload naming the same game twice.

Tables repaired:
  2025_schedule    167 -> 162
  2025_game_info   167 -> 162

line_score_innings and individual_batting_stats are fine -- they hold many rows
per game by design, and cover exactly 162 distinct gamePks.

regular_season.py no longer produces duplicates, so a rebuilt table is already
correct. This is for a database built before that fix. It repairs in place
rather than rebuilding, because regular_season.py drops 2025_schedule and
recreates it with 4 columns, which would discard the ~40 enrichment columns the
later scripts add.

Idempotent: re-running on repaired tables changes nothing.

    ./myenv/bin/python sox_2025/scripts/dedupe_games.py [--db PATH] [--dry-run]

Back up the database first. It is ~75MB and expensive to rebuild.
"""

import argparse
import sys

import duckdb

SCHEDULE = 'main."2025_schedule"'
GAME_INFO = 'main."2025_game_info"'

# In 2025_schedule, four pairs differ only in gameDate and doubleheader -- every
# other column is identical, so dropping the superseded row loses nothing.
LOSSLESS = (777294, 777815, 778179, 778443)

# 777809 is the exception in both tables. Its two rows have enrichment split
# across them, because the enrichment scripts UPDATE ... WHERE s.gamePk =
# u.gamePk and DuckDB picks arbitrarily when two rows match. The row carrying
# the wrong date holds the correct score, daynight and start time.
# MLB: gamePk 777809 is Final 2025-05-24T17:05Z, home 6 away 5.
MERGE_PK = 777809
MERGE_DROP_DATE = "2025-05-24"  # the schedule row to drop, by its gameDate
MERGE_KEEP_DATE = "2025-05-24 13:05:00"  # the date the survivor should carry

# Never a doubleheader. It got flagged because 777294 -- suspended on 7/01 --
# was resumed on 7/02, so that date block reported totalGames = 2. MLB reports
# doubleHeader "N" for both games that day.
NOT_A_DOUBLEHEADER = 777277


def counts(conn, table):
    return conn.execute(f"SELECT COUNT(*), COUNT(DISTINCT gamePk) FROM {table}").fetchone()


def dedupe_schedule(conn):
    """2025_schedule has a gameDate, so the official date picks the survivor."""
    placeholders = ", ".join(str(pk) for pk in LOSSLESS)
    conn.execute(f"""
        DELETE FROM {SCHEDULE}
        WHERE gamePk IN ({placeholders})
          AND CAST(gameDate AS DATE) <> officialDate
    """)
    conn.execute(f"""
        DELETE FROM {SCHEDULE}
        WHERE gamePk = {MERGE_PK} AND CAST(gameDate AS DATE) = DATE '{MERGE_DROP_DATE}'
    """)
    conn.execute(f"""
        UPDATE {SCHEDULE} SET gameDate = TIMESTAMP '{MERGE_KEEP_DATE}'
        WHERE gamePk = {MERGE_PK}
    """)
    conn.execute(f"UPDATE {SCHEDULE} SET doubleheader = FALSE WHERE gamePk = {NOT_A_DOUBLEHEADER}")


def dedupe_game_info(conn):
    """2025_game_info has no gameDate -- four of the five pairs are exact
    duplicates, so any survivor will do. Only 777809 differs, and there the
    scored row is the real one, so a null score sorts last."""
    conn.execute(f"""
        DELETE FROM {GAME_INFO} WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid, ROW_NUMBER() OVER (
                    PARTITION BY gamePk ORDER BY (home_score IS NULL), rowid
                ) AS rn
                FROM {GAME_INFO}
            ) WHERE rn = 1
        )
    """)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="redsox_25.duckdb")
    parser.add_argument("--dry-run", action="store_true", help="roll back instead of committing")
    args = parser.parse_args()

    conn = duckdb.connect(args.db)
    todo = []
    for table, fn in ((SCHEDULE, dedupe_schedule), (GAME_INFO, dedupe_game_info)):
        rows, distinct = counts(conn, table)
        print(f"before: {table:26} {rows} rows, {distinct} distinct gamePk")
        if rows != distinct:
            todo.append((table, fn))

    if not todo:
        print("nothing to do -- every table already has one row per gamePk")
        return 0

    conn.execute("BEGIN TRANSACTION")
    try:
        for table, fn in todo:
            fn(conn)
            rows, distinct = counts(conn, table)
            if rows != distinct:
                raise AssertionError(f"{table}: still {rows} rows for {distinct} gamePks")
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    suffix = " (rolled back -- dry run)" if args.dry_run else ""
    for table, _ in todo:
        rows, distinct = counts(conn, table)
        print(f"after:  {table:26} {rows} rows, {distinct} distinct gamePk{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
