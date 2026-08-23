"""One-time repair: collapse duplicate gamePk rows in 2025_schedule.

The MLB schedule API lists a postponed game under both its original date block
and its makeup date block, under one gamePk. regular_season.py used to append
every entry, which put 167 rows in the table for 162 games. That broke
watch-history saves outright -- the PUT payload repeated those gamePks, and the
API rejects a payload naming the same game twice.

regular_season.py no longer does this, so a rebuilt table is already correct.
This is for a database built before that fix. It repairs in place rather than
rebuilding, because regular_season.py drops the table and recreates it with 4
columns, which would discard the ~40 enrichment columns the later scripts add.

Idempotent: re-running on a repaired table changes nothing.

    ./myenv/bin/python sox_2025/scripts/dedupe_schedule.py [--db PATH] [--dry-run]

Back up the database first. It is ~75MB and expensive to rebuild.
"""

import argparse
import sys

import duckdb

TABLE = 'main."2025_schedule"'

# Four pairs differ only in gameDate and doubleheader -- every other column is
# identical, so dropping the superseded row loses nothing.
LOSSLESS = (777294, 777815, 778179, 778443)

# 777809 is the exception. Its two rows have enrichment split across them: the
# row carrying the wrong date holds the correct score, daynight and start time,
# because the enrichment scripts UPDATE ... WHERE s.gamePk = u.gamePk and
# DuckDB picks arbitrarily when two rows match. Keep the enriched row and give
# it the right date. MLB: gamePk 777809 is Final 2025-05-24T17:05Z, home 6 away 5.
MERGE_PK = 777809
MERGE_DROP_DATE = "2025-05-24"  # the row to drop, by its gameDate
MERGE_KEEP_DATE = "2025-05-24 13:05:00"  # the date the surviving row should carry

# Never a doubleheader. It got flagged because 777294 -- suspended on 7/01 --
# was resumed on 7/02, so that date block reported totalGames = 2. MLB reports
# doubleHeader "N" for both games that day.
NOT_A_DOUBLEHEADER = 777277


def counts(conn):
    return conn.execute(f"SELECT COUNT(*), COUNT(DISTINCT gamePk) FROM {TABLE}").fetchone()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="redsox_25.duckdb")
    parser.add_argument("--dry-run", action="store_true", help="roll back instead of committing")
    args = parser.parse_args()

    conn = duckdb.connect(args.db)
    rows, distinct = counts(conn)
    print(f"before: {rows} rows, {distinct} distinct gamePk")

    if rows == distinct:
        print("nothing to do -- already one row per gamePk")
        return 0

    conn.execute("BEGIN TRANSACTION")
    try:
        placeholders = ", ".join(str(pk) for pk in LOSSLESS)
        conn.execute(f"""
            DELETE FROM {TABLE}
            WHERE gamePk IN ({placeholders})
              AND CAST(gameDate AS DATE) <> officialDate
        """)
        conn.execute(f"""
            DELETE FROM {TABLE}
            WHERE gamePk = {MERGE_PK}
              AND CAST(gameDate AS DATE) = DATE '{MERGE_DROP_DATE}'
        """)
        conn.execute(f"""
            UPDATE {TABLE} SET gameDate = TIMESTAMP '{MERGE_KEEP_DATE}'
            WHERE gamePk = {MERGE_PK}
        """)
        conn.execute(f"UPDATE {TABLE} SET doubleheader = FALSE WHERE gamePk = {NOT_A_DOUBLEHEADER}")

        rows, distinct = counts(conn)
        if rows != distinct:
            raise AssertionError(f"still {rows} rows for {distinct} gamePks -- not committing")

        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    print(f"after:  {rows} rows, {distinct} distinct gamePk"
          f"{' (rolled back -- dry run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
