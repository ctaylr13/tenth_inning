import duckdb
import pandas as pd
from typing import Optional

DB_PATH = "../../redsox_25.duckdb"
MANAGERS_TABLE = 'redsox_25.main."2025_managers"'
SCHEDULE_TABLE = 'redsox_25.main."2025_schedule"'

def build_manager_ranges(df_mgr: pd.DataFrame) -> pd.DataFrame:
    df = df_mgr.copy().sort_values(["manager_team_id","Rk"], na_position="last")
    df["G"] = df["G"].fillna(0).astype(int)
    df["cum_games"] = df.groupby("manager_team_id")["G"].cumsum()
    df["range_start"] = df["cum_games"] - df["G"] + 1
    df.loc[df["G"] == 0, "range_start"] = 10**9
    return df

def pick_manager_name_for_gamesplayed(df_ranges: pd.DataFrame, team_id: Optional[int], gp: Optional[int]) -> Optional[str]:
    if team_id is None or pd.isna(team_id):
        return None
    team_rows = df_ranges[df_ranges["manager_team_id"] == int(team_id)]
    if team_rows.empty:
        return None
    if gp is not None and not pd.isna(gp):
        match = team_rows[(team_rows["range_start"] <= int(gp)) & (team_rows["cum_games"] >= int(gp))]
        if not match.empty:
            return match.iloc[0]["Mgr"]
    full_season = team_rows[team_rows["G"] >= 162]
    if not full_season.empty:
        return full_season.iloc[0]["Mgr"]
    return team_rows.iloc[0]["Mgr"]

def main():
    conn = duckdb.connect(DB_PATH)
    try:
        df_mgr = conn.execute(f'SELECT Rk, Mgr, Tm, G, manager_team_id FROM {MANAGERS_TABLE}').fetchdf()
        if df_mgr.empty:
            print("No managers found.")
            return
        df_ranges = build_manager_ranges(df_mgr)
        df_sched = conn.execute(f'SELECT gamePk, home_team_id, away_team_id, home_gamesPlayed, away_gamesPlayed FROM {SCHEDULE_TABLE}').fetchdf()
        if df_sched.empty:
            print("No schedule rows found.")
            return

        out_rows = []
        for _, r in df_sched.iterrows():
            gamePk = int(r["gamePk"])
            home_mgr_name = pick_manager_name_for_gamesplayed(df_ranges, r["home_team_id"], r.get("home_gamesPlayed"))
            away_mgr_name = pick_manager_name_for_gamesplayed(df_ranges, r["away_team_id"], r.get("away_gamesPlayed"))
            out_rows.append({"gamePk": gamePk, "home_manager": home_mgr_name, "away_manager": away_mgr_name})

        df_out = pd.DataFrame(out_rows)

        # ensure columns exist on schedule
        tbl = SCHEDULE_TABLE.split('.',1)[1]
        existing = {c[1] for c in conn.execute(f'PRAGMA table_info({tbl})').fetchall()}
        if "home_manager" not in existing:
            conn.execute(f'ALTER TABLE {SCHEDULE_TABLE} ADD COLUMN home_manager VARCHAR')
        if "away_manager" not in existing:
            conn.execute(f'ALTER TABLE {SCHEDULE_TABLE} ADD COLUMN away_manager VARCHAR')

        # upsert via temp table
        conn.register("tmp_mgrs", df_out)
        conn.execute("""
        CREATE TEMPORARY TABLE tmp_mgr_updates AS
        SELECT CAST(gamePk AS BIGINT) AS gamePk,
            CAST(home_manager AS VARCHAR) AS home_manager,
            CAST(away_manager AS VARCHAR) AS away_manager
        FROM tmp_mgrs
        """)
        conn.execute(f'''
        UPDATE {SCHEDULE_TABLE} AS s
        SET
        home_manager = COALESCE(t.home_manager, s.home_manager),
        away_manager = COALESCE(t.away_manager, s.away_manager)
        FROM tmp_mgr_updates t
        WHERE s.gamePk = t.gamePk
        ''')
        conn.unregister("tmp_mgrs")
        conn.execute("DROP TABLE IF EXISTS tmp_mgr_updates")
        print("Updated schedule with manager names for", len(df_out), "games.")
    finally:
        conn.close()

main()