import time, json
import requests
import pandas as pd
import duckdb
from typing import Dict, Any

#this script has some extra stuff we dont need the bench players maybe? 

DB_PATH = "../../redsox_25.duckdb"
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
USER_AGENT = "tenth-inning-script/1.0 (6282920+ctaylr13@users.noreply.github.com)"

def safe_get(d: Dict[Any, Any], *path, default=None):
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

existing = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
game_pks = existing["gamePk"].astype(int).tolist()

rows = []
candidates = [
    ("gameData", "players"),
    ("gameData", "teams", "away", "players"),
    ("gameData", "teams", "home", "players"),
    ("teams", "away", "players"),
    ("teams", "home", "players"),
    ("liveData", "boxscore", "teams", "away", "players"),
    ("liveData", "boxscore", "teams", "home", "players"),
]

total = len(game_pks)
for idx, pk in enumerate(game_pks, start=1):
    try:
        r = session.get(GAME_URL.format(pk=pk), timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[{idx}/{total}] Fetch error for {pk}: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    players = {}
    for path in candidates:
        p = safe_get(payload, *path)
        if isinstance(p, dict):
            players.update(p)

    if not players:
        print(f"[{idx}/{total}] {pk}: no players found")
        time.sleep(SLEEP_SECONDS)
        continue

    starters_count = 0
    for key, p in players.items():
        person = safe_get(p, "person") or {}
        try:
            pid = safe_get(person, "id")
            pid = int(pid) if pid is not None else None
        except Exception:
            pid = None

        batting_order = safe_get(p, "battingOrder")
        is_starter = False
        if batting_order not in (None, "", []):
            # treat presence of a battingOrder value as starter
            is_starter = True
            starters_count += 1

        rows.append({
            "gamePk": int(pk),
            "player_key": key,
            "playerId": pid,
            "fullName": safe_get(person, "fullName"),
            "jerseyNumber": safe_get(p, "jerseyNumber"),
            "parentTeamId": safe_get(p, "parentTeamId"),
            "position_name": safe_get(p, "position", "name"),
            "position_abbr": safe_get(p, "position", "abbreviation"),
            "battingOrder": batting_order,
            "is_starter": is_starter
        })

    print(f"[{idx}/{total}] Processed {pk}: players={len(players)}, starters={starters_count}")
    time.sleep(SLEEP_SECONDS)

if not rows:
    print("No roster rows collected.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(rows)

conn.execute("""
CREATE TABLE IF NOT EXISTS game_rosters (
  gamePk BIGINT,
  player_key VARCHAR,
  playerId INTEGER,
  fullName VARCHAR,
  jerseyNumber VARCHAR,
  parentTeamId INTEGER,
  position_name VARCHAR,
  position_abbr VARCHAR,
  battingOrder VARCHAR,
  is_starter BOOLEAN
)
""")

gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
if gamepk_list:
    conn.execute(f"DELETE FROM game_rosters WHERE gamePk IN ({gamepk_list})")

conn.register("tmp_rosters", df)
conn.execute("""
INSERT INTO game_rosters
SELECT
  CAST(gamePk AS BIGINT),
  player_key,
  CAST(playerId AS INTEGER),
  fullName,
  jerseyNumber,
  CAST(parentTeamId AS INTEGER),
  position_name,
  position_abbr,
  battingOrder,
  CAST(is_starter AS BOOLEAN)
FROM tmp_rosters
""")
conn.unregister("tmp_rosters")

print("Inserted", len(df), "rows into game_rosters")
conn.close()
