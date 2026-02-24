import duckdb
import pandas as pd
from typing import Optional

DB_PATH = "../../redsox_25.duckdb"
TABLE = 'redsox_25.main."individual_pitching_stats"'

def format_innings_display(outs: Optional[int]) -> Optional[str]:
    if outs is None:
        return None
    try:
        outs = int(outs)
    except Exception:
        return None
    innings = outs // 3
    rem = outs % 3
    return f"{innings}.{rem}"  # e.g. 14 outs -> "4.2" (4 and 2/3)

def main():
    conn = duckdb.connect(DB_PATH)
    try:
        # Read needed columns
        df = conn.execute(f"SELECT gamePk, playerId, outs FROM {TABLE}").fetchdf()
        if df.empty:
            print("No rows found in table.")
            return
            # Compute columns
        df["innings_pitched"] = df["outs"].apply(lambda o: None if pd.isna(o) else float(o) / 3.0)
        df["innings_pitched_display"] = df["outs"].apply(lambda o: format_innings_display(None if pd.isna(o) else o))

        # Ensure columns exist
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE.split('.',1)[1]})").fetchall()}
        if "innings_pitched" not in cols:
            conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN innings_pitched DOUBLE')
            print("Added column innings_pitched")
        if "innings_pitched_display" not in cols:
            conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN innings_pitched_display VARCHAR')
            print("Added column innings_pitched_display")

        # Prepare temp table and update
        conn.register("tmp_ips", df[["gamePk", "playerId", "innings_pitched", "innings_pitched_display"]])
        conn.execute("""
        CREATE TEMPORARY TABLE tmp_ips_upd AS
        SELECT CAST(gamePk AS BIGINT) AS gamePk,
            CAST(playerId AS BIGINT) AS playerId,
            CAST(innings_pitched AS DOUBLE) AS innings_pitched,
            innings_pitched_display
        FROM tmp_ips
        """)
        conn.execute(f"""
        UPDATE {TABLE} AS s
        SET
        innings_pitched = COALESCE(t.innings_pitched, s.innings_pitched),
        innings_pitched_display = COALESCE(t.innings_pitched_display, s.innings_pitched_display)
        FROM tmp_ips_upd t
        WHERE s.gamePk = t.gamePk AND s.playerId = t.playerId
        """)
        conn.unregister("tmp_ips")
        conn.execute("DROP TABLE IF EXISTS tmp_ips_upd")
        print("Updated innings_pitched and innings_pitched_display for", len(df), "rows.")
    finally:
        conn.close()


main()