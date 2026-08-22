import time
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
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

# read gamePk list
existing = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
game_pks = existing["gamePk"].astype(int).tolist()
print("Found", len(game_pks), "gamePk(s) in DB")

rows = []
for pk in game_pks:
    url = GAME_URL.format(pk=pk)
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"Fetch error for {pk}: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    officials = safe_get(payload, "gameData", "officials") or []
    # default None for each base
    homeplate = firstbase = secondbase = thirdbase = None
    for o in officials:
        typ = safe_get(o, "officialType")
        oid = safe_get(o, "official", "id")
        if oid is not None:
            try:
                oid = int(oid)
            except Exception:
                oid = None
        if typ == "Home Plate":
            homeplate = oid
        elif typ == "First Base":
            firstbase = oid
        elif typ == "Second Base":
            secondbase = oid
        elif typ == "Third Base":
            thirdbase = oid

    rows.append({
        "gamePk": int(safe_get(payload, "gamePk") or pk),
        "homeplate": homeplate,
        "firstbase": firstbase,
        "secondbase": secondbase,
        "thirdbase": thirdbase,
    })

    time.sleep(SLEEP_SECONDS)

if not rows:
    print("No rows fetched from API.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(rows)
existing_set = set(game_pks)
df = df[df["gamePk"].isin(existing_set)]
if df.empty:
    print("No matching rows to insert after filtering.")
    conn.close()
    raise SystemExit(0)

# create table if not exists
conn.execute("""
CREATE TABLE IF NOT EXISTS umpire_game_stats (
    gamePk BIGINT PRIMARY KEY,
    homeplate INTEGER,
    firstbase INTEGER,
    secondbase INTEGER,
    thirdbase INTEGER
)
""")

# delete existing rows for these gamePks to make insert idempotent
gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
if gamepk_list:
    conn.execute(f"DELETE FROM umpire_game_stats WHERE gamePk IN ({gamepk_list})")

# insert rows
conn.register("tmp_umpire_updates", df)
conn.execute("""
INSERT INTO umpire_game_stats
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(homeplate AS INTEGER) AS homeplate,
  CAST(firstbase AS INTEGER) AS firstbase,
  CAST(secondbase AS INTEGER) AS secondbase,
  CAST(thirdbase AS INTEGER) AS thirdbase
FROM tmp_umpire_updates
""")
conn.unregister("tmp_umpire_updates")

print("Inserted", len(df), "rows into umpire_game_stats")
conn.close()
