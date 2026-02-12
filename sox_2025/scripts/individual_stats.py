import time
import json
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
USER_AGENT = "tenth-inning-script/1.0 (ctaylr13@gmail.com)"

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

def dedupe_preserve_order(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
conn = duckdb.connect(DB_PATH)

game_pks = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist()
total = len(game_pks)

bat_int_cols = [
  "gamesPlayed","flyOuts","groundOuts","airOuts","runs","doubles","triples","homeRuns",
  "strikeOuts","baseOnBalls","intentionalWalks","hits","hitByPitch","atBats",
  "caughtStealing","stolenBases","groundIntoDoublePlay","groundIntoTriplePlay",
  "plateAppearances","totalBases","rbi","leftOnBase","sacBunts","sacFlies",
  "catchersInterference","pickoffs","popOuts","lineOuts"
]
bat_float_cols = ["avg","obp","slg","ops","babip","groundOutsToAirouts","atBatsPerHomeRun"]

pit_int_cols = [
  "gamesPlayed","gamesStarted","flyOuts","groundOuts","airOuts","runs","doubles","triples","homeRuns",
  "strikeOuts","baseOnBalls","intentionalWalks","hits","hitByPitch","atBats",
  "caughtStealing","stolenBases","numberOfPitches","wins","losses","saves","saveOpportunities",
  "holds","blownSaves","earnedRuns","battersFaced","outs","gamesPitched","completeGames",
  "shutouts","balls","strikes","hitBatsmen","balks","wildPitches","pickoffs","rbi",
  "gamesFinished","popOuts","lineOuts","inheritedRunners","inheritedRunnersScored"
]
pit_float_cols = [
  "obp","era","whip","strikePercentage","groundOutsToAirouts","winPercentage",
  "pitchesPerInning","strikeoutWalkRatio","strikeoutsPer9Inn","walksPer9Inn",
  "hitsPer9Inn","runsScoredPer9","homeRunsPer9"
]

fld_int_cols = [
  "caughtStealing","stolenBases","assists","putOuts","errors","chances","passedBall","pickoffs"
]
fld_float_cols = ["stolenBasePercentage","caughtStealingPercentage","fielding"]

# dedupe column lists (preserve order)
bat_int_cols = dedupe_preserve_order(bat_int_cols)
bat_float_cols = dedupe_preserve_order(bat_float_cols)
pit_int_cols = dedupe_preserve_order(pit_int_cols)
pit_float_cols = dedupe_preserve_order(pit_float_cols)
fld_int_cols = dedupe_preserve_order(fld_int_cols)
fld_float_cols = dedupe_preserve_order(fld_float_cols)

bat_rows = []
pit_rows = []
fld_rows = []

for idx, pk in enumerate(game_pks, start=1):
    try:
        r = session.get(GAME_URL.format(pk=pk), timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[{idx}/{total}] {pk} - fetch error: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    cb = cp = cf = 0
    for side in ("away", "home"):
        players = safe_get(payload, "liveData", "boxscore", "teams", side, "players") or {}
        for _, pdata in players.items():
            pid = safe_get(pdata, "person", "id")
            stats_obj = safe_get(pdata, "stats") or {}
            batting = safe_get(stats_obj, "batting") or {}
            pitching = safe_get(stats_obj, "pitching") or {}
            fielding = safe_get(stats_obj, "fielding") or {}

            if isinstance(batting, dict) and batting:
                row = {"gamePk": int(pk), "playerId": int(pid) if pid is not None else None, "team_side": side}
                for k in bat_int_cols + bat_float_cols:
                    row[k] = batting.get(k)
                extras = {k: v for k, v in batting.items() if k not in set(row.keys())}
                row["bat_extra"] = None if not extras else json.dumps(extras)
                bat_rows.append(row); cb += 1

            if isinstance(pitching, dict) and pitching:
                row = {"gamePk": int(pk), "playerId": int(pid) if pid is not None else None, "team_side": side}
                for k in pit_int_cols + pit_float_cols:
                    row[k] = pitching.get(k)
                extras = {k: v for k, v in pitching.items() if k not in set(row.keys())}
                row["pit_extra"] = None if not extras else json.dumps(extras)
                pit_rows.append(row); cp += 1

            if isinstance(fielding, dict) and fielding:
                row = {"gamePk": int(pk), "playerId": int(pid) if pid is not None else None, "team_side": side}
                for k in fld_int_cols + fld_float_cols:
                    row[k] = fielding.get(k)
                extras = {k: v for k, v in fielding.items() if k not in set(row.keys())}
                row["fld_extra"] = None if not extras else json.dumps(extras)
                fld_rows.append(row); cf += 1

    print(f"[{idx}/{total}] {pk} - batting={cb} pitching={cp} fielding={cf}")
    time.sleep(SLEEP_SECONDS)

# Create tables (explicit columns with types). extras column VARCHAR for anything else.
conn.execute(f'''
CREATE TABLE IF NOT EXISTS batting (
  gamePk BIGINT,
  playerId INTEGER,
  team_side VARCHAR,
  {', '.join(f'"{c}" INTEGER' for c in bat_int_cols)},
  {', '.join(f'"{c}" DOUBLE' for c in bat_float_cols)},
  bat_extra VARCHAR
)
''')
conn.execute(f'''
CREATE TABLE IF NOT EXISTS individual_pitching_stats (
  gamePk BIGINT,
  playerId INTEGER,
  team_side VARCHAR,
  {', '.join(f'"{c}" INTEGER' for c in pit_int_cols)},
  {', '.join(f'"{c}" DOUBLE' for c in pit_float_cols)},
  pit_extra VARCHAR
)
''')
conn.execute(f'''
CREATE TABLE IF NOT EXISTS individual_fielding_stats (
  gamePk BIGINT,
  playerId INTEGER,
  team_side VARCHAR,
  {', '.join(f'"{c}" INTEGER' for c in fld_int_cols)},
  {', '.join(f'"{c}" DOUBLE' for c in fld_float_cols)},
  fld_extra VARCHAR
)
''')

def upsert(table_name: str, rows: list, int_cols, float_cols, extra_col):
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
    if gamepk_list:
        conn.execute(f"DELETE FROM {table_name} WHERE gamePk IN ({gamepk_list})")
    conn.register("tmp_upd", df)

    select_parts = [
        "CAST(gamePk AS BIGINT) AS gamePk",
        "CAST(playerId AS INTEGER) AS playerId",
        "team_side"
    ]
    for c in int_cols:
        select_parts.append(f"TRY_CAST(\"{c}\" AS INTEGER) AS \"{c}\"")
    for c in float_cols:
        select_parts.append(f"TRY_CAST(\"{c}\" AS DOUBLE) AS \"{c}\"")
    select_parts.append(f"{extra_col}")

    select_sql = ", ".join(select_parts)
    conn.execute(f"INSERT INTO {table_name} SELECT {select_sql} FROM tmp_upd")
    conn.unregister("tmp_upd")
    return len(df)

n_bat = upsert("batting", bat_rows, bat_int_cols, bat_float_cols, "bat_extra")
n_pit = upsert("individual_pitching_stats", pit_rows, pit_int_cols, pit_float_cols, "pit_extra")
n_fld = upsert("individual_fielding_stats", fld_rows, fld_int_cols, fld_float_cols, "fld_extra")

print(f"Inserted {n_bat} batting rows, {n_pit} pitching rows, {n_fld} fielding rows.")
conn.close()
