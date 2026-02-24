import duckdb
import pandas as pd
from datetime import timedelta
from typing import List

DB_PATH = "../../redsox_25.duckdb"
SOURCE_TABLE = 'main."2025_schedule"'
TMP_TABLE = "tmp_schedule_times"

def safe_add_columns(conn: duckdb.DuckDBPyConnection, cols: List[tuple]):
    # cols: list of (name, sql_type)
    existing = {r[1] for r in conn.execute("PRAGMA table_info('2025_schedule')").fetchall()}
    for name, sql_type in cols:
        if name not in existing:
            conn.execute(f'ALTER TABLE {SOURCE_TABLE} ADD COLUMN {name} {sql_type}')

def compute_times(df: pd.DataFrame) -> pd.DataFrame:
    # parse gameDate into datetime (pandas handles ISO + timezone)
    df = df.copy()
    df["game_start"] = pd.to_datetime(df["gameDate"], errors="coerce")
    # compute end by adding gameDurationMinutes (if available)
    def compute_end(row):
        start = row["game_start"]
        mins = row.get("gameDurationMinutes")
        if pd.isna(start) or mins is None:
            return pd.NaT
        try:
            mins_f = float(mins)
        except Exception:
            return pd.NaT
        return start + pd.to_timedelta(mins_f, unit="m")
    df["game_end"] = df.apply(compute_end, axis=1)
    # create 12-hour strings, e.g. "7:05 PM"
    # If timezone-aware datetime has tzinfo, strftime will include localized time appropriately.
    def fmt_12h(ts):
        if pd.isna(ts):
            return None
        try:
            # use %-I on Unix for no-leading-zero hour; on Windows use %#I — use fallback
            s = ts.strftime("%-I:%M %p") if hasattr(ts, "strftime") else str(ts)
        except Exception:
            # fallback safe formatting with leading zero then strip
            s = ts.strftime("%I:%M %p")
            if s.startswith("0"):
                s = s[1:]
        return s
    df["game_start_12hr"] = df["game_start"].apply(lambda x: fmt_12h(x))
    df["game_end_12hr"] = df["game_end"].apply(lambda x: fmt_12h(x))
    return df[["gamePk", "game_start", "game_end", "game_start_12hr", "game_end_12hr"]]

def main():
    conn = duckdb.connect(DB_PATH)
    try:
        # read only the minimal columns to compute times
        df_src = conn.execute(f"SELECT gamePk, gameDate, gameDurationMinutes FROM {SOURCE_TABLE}").fetchdf()
        if df_src.empty:
            print("No rows found in source table.")
            return
        df_times = compute_times(df_src)

        # ensure columns exist on the existing table
        columns_to_add = [
            ("game_start", "TIMESTAMP"),
            ("game_end", "TIMESTAMP"),
            ("game_start_12hr", "VARCHAR"),
            ("game_end_12hr", "VARCHAR"),
        ]
        safe_add_columns(conn, columns_to_add)

        # write temp table with computed values
        conn.register("tmp_times_df", df_times)
        conn.execute(f"CREATE OR REPLACE TEMPORARY TABLE {TMP_TABLE} AS SELECT * FROM tmp_times_df")
        conn.unregister("tmp_times_df")

        # update existing table with computed columns (use direct assignment)
        conn.execute(f"""
        UPDATE {SOURCE_TABLE} AS s
        SET
        game_start = t.game_start,
        game_end = t.game_end,
        game_start_12hr = t.game_start_12hr,
        game_end_12hr = t.game_end_12hr
        FROM {TMP_TABLE} t
        WHERE s.gamePk = t.gamePk
        """)

        # drop temp table
        conn.execute(f"DROP TABLE IF EXISTS {TMP_TABLE}")

        print(f"Updated {len(df_times)} rows with game_start/game_end and 12-hour columns.")
    finally:
        conn.close()

main()