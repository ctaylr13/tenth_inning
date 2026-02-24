import ast
import time
import pandas as pd
import duckdb
from typing import List, Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"
GAME_ROLES_TABLE = 'redsox_25.main."game_roles"'
PITCH_STATS_TABLE = 'redsox_25.main."individual_pitching_stats"'
BATCH_SLEEP = 0.01  # pause between games

def parse_pitcher_list(s: Optional[str]) -> List[int]:
    if s is None:
        return []
    s = str(s).strip()
    if s == "" or s.lower() == "null":
        return []
    try:
        vals = ast.literal_eval(s)
        return [int(x) for x in vals] if isinstance(vals, (list, tuple)) else []
    except Exception:
        s2 = s.strip("[]")
        parts = [p.strip() for p in s2.split(",") if p.strip() != ""]
        out = []
        for p in parts:
            try:
                out.append(int(p))
            except Exception:
                pass
        return out

def build_order_map(lst: List[int]) -> Dict[int, int]:
    return {pid: idx + 1 for idx, pid in enumerate(lst)}  # 1-based

def ensure_pitcher_order_column(conn: duckdb.DuckDBPyConnection):
    tbl = PITCH_STATS_TABLE.split('.',1)[1]
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
    if "pitcher_order" not in cols:
        conn.execute(f'ALTER TABLE {PITCH_STATS_TABLE} ADD COLUMN pitcher_order INTEGER')
        print("Added column pitcher_order to", PITCH_STATS_TABLE)

def main():
    conn = duckdb.connect(DB_PATH)
    try:
        df_roles = conn.execute(f"""
            SELECT gamePk, pitchers_away, pitchers_home
            FROM {GAME_ROLES_TABLE}
            WHERE gamePk IS NOT NULL
        """).fetchdf()
        if df_roles.empty:
            print("No game_roles rows found.")
            return
        ensure_pitcher_order_column(conn)

        total_mappings = 0
        for _, row in df_roles.iterrows():
            gamePk = int(row["gamePk"])
            away_text = row.get("pitchers_away")
            home_text = row.get("pitchers_home")

            away_list = parse_pitcher_list(away_text)
            home_list = parse_pitcher_list(home_text)

            away_map = build_order_map(away_list)
            home_map = build_order_map(home_list)

            updates = []
            for pid, ordn in away_map.items():
                updates.append({"gamePk": gamePk, "playerId": pid, "pitcher_order": ordn})
            for pid, ordn in home_map.items():
                updates.append({"gamePk": gamePk, "playerId": pid, "pitcher_order": ordn})

            if not updates:
                continue

            df_up = pd.DataFrame(updates)
            conn.register("tmp_pitch_order", df_up)
            conn.execute("""
            CREATE TEMPORARY TABLE tmp_pitch_order_sched AS
            SELECT CAST(gamePk AS BIGINT) AS gamePk,
                CAST(playerId AS BIGINT) AS playerId,
                CAST(pitcher_order AS INTEGER) AS pitcher_order
            FROM tmp_pitch_order
            """)
            conn.execute(f"""
            UPDATE {PITCH_STATS_TABLE} AS s
            SET pitcher_order = t.pitcher_order
            FROM tmp_pitch_order_sched t
            WHERE s.gamePk = t.gamePk AND s.playerId = t.playerId
            """)
            conn.unregister("tmp_pitch_order")
            conn.execute("DROP TABLE IF EXISTS tmp_pitch_order_sched")

            total_mappings += len(df_up)
            time.sleep(BATCH_SLEEP)

        print("Done. Total pitcher_order mappings applied:", total_mappings)
    finally:
        conn.close()

main()