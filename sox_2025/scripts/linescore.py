import time
import json
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"
LINESCORE_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/linescore"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
USER_AGENT = "tenth-inning-script/1.0 (6282920+ctaylr13@users.noreply.github.com)"

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
conn = duckdb.connect(DB_PATH)

# get gamePk list
game_pks = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist()
total = len(game_pks)

innings_rows = []
totals_rows = []

for idx, pk in enumerate(game_pks, start=1):
    try:
        r = session.get(LINESCORE_URL.format(pk=pk), timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[{idx}/{total}] {pk} - fetch error: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    innings = safe_get(payload, "innings") or []
    teams_tot = safe_get(payload, "teams") or {}

    # collect inning rows
    for inn in innings:
        inning_num = safe_get(inn, "num")
        ordinal = safe_get(inn, "ordinalNum")
        home = safe_get(inn, "home") or {}
        away = safe_get(inn, "away") or {}

        innings_rows.append({
            "gamePk": int(pk),
            "inning_num": inning_num,
            "ordinalNum": ordinal,
            "home_runs": safe_get(home, "runs"),
            "home_hits": safe_get(home, "hits"),
            "home_errors": safe_get(home, "errors"),
            "home_leftOnBase": safe_get(home, "leftOnBase"),
            "away_runs": safe_get(away, "runs"),
            "away_hits": safe_get(away, "hits"),
            "away_errors": safe_get(away, "errors"),
            "away_leftOnBase": safe_get(away, "leftOnBase")
        })

    # collect totals
    home_tot = safe_get(teams_tot, "home") or {}
    away_tot = safe_get(teams_tot, "away") or {}
    totals_rows.append({
        "gamePk": int(pk),
        "home_runs": safe_get(home_tot, "runs"),
        "home_hits": safe_get(home_tot, "hits"),
        "home_errors": safe_get(home_tot, "errors"),
        "home_leftOnBase": safe_get(home_tot, "leftOnBase"),
        "home_isWinner": safe_get(home_tot, "isWinner"),
        "away_runs": safe_get(away_tot, "runs"),
        "away_hits": safe_get(away_tot, "hits"),
        "away_errors": safe_get(away_tot, "errors"),
        "away_leftOnBase": safe_get(away_tot, "leftOnBase"),
        "away_isWinner": safe_get(away_tot, "isWinner")
    })

    print(f"[{idx}/{total}] {pk} - innings={len(innings)} totals_collected")
    time.sleep(SLEEP_SECONDS)

# create tables if missing
conn.execute("""
CREATE TABLE IF NOT EXISTS line_score_innings (
  gamePk BIGINT,
  inning_num INTEGER,
  ordinalNum VARCHAR,
  home_runs INTEGER,
  home_hits INTEGER,
  home_errors INTEGER,
  home_leftOnBase INTEGER,
  away_runs INTEGER,
  away_hits INTEGER,
  away_errors INTEGER,
  away_leftOnBase INTEGER
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS line_score_totals (
  gamePk BIGINT PRIMARY KEY,
  home_runs INTEGER,
  home_hits INTEGER,
  home_errors INTEGER,
  home_leftOnBase INTEGER,
  home_isWinner BOOLEAN,
  away_runs INTEGER,
  away_hits INTEGER,
  away_errors INTEGER,
  away_leftOnBase INTEGER,
  away_isWinner BOOLEAN
)
""")

# upsert (delete existing rows for these gamePks and insert)
def upsert_table(table_name: str, rows: list, pk_col="gamePk"):
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
    if gamepk_list:
        conn.execute(f"DELETE FROM {table_name} WHERE gamePk IN ({gamepk_list})")
    conn.register("tmp_upd", df)
    cols = ", ".join(df.columns)
    conn.execute(f"INSERT INTO {table_name} ({cols}) SELECT {cols} FROM tmp_upd")
    conn.unregister("tmp_upd")
    return len(df)

n_inn = upsert_table("line_score_innings", innings_rows)
n_tot = upsert_table("line_score_totals", totals_rows)
print(f"Inserted {n_inn} inning rows and {n_tot} total rows.")
conn.close()
