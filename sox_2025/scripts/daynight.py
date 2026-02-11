import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"
BASE_URL = "https://statsapi.mlb.com/api/v1/schedule"
HYDRATE = "team"
SPORT_ID = 1
START_DATE = "2025-03-27"
END_DATE = "2025-09-30"
TIMEOUT = 60

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

# fetch schedule (teams hydrated)
params = {
    "hydrate": HYDRATE,
    "sportId": SPORT_ID,
    "startDate": START_DATE,
    "endDate": END_DATE,
}
resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
resp.raise_for_status()
payload = resp.json()

rows = []
for date_block in payload.get("dates", []):
    for game in date_block.get("games", []):
        pk = game.get("gamePk")
        # dayNight can be at top-level or under status
        daynight = safe_get(game, "dayNight") or safe_get(game, "status", "dayNight")
        if pk is not None:
            rows.append({"gamePk": int(pk), "daynight": daynight})

if not rows:
    print("No rows fetched.")
    raise SystemExit(0)

df = pd.DataFrame(rows)
print("Fetched rows:", len(df))

conn = duckdb.connect(DB_PATH)

# ensure table exists
conn.execute('PRAGMA show_tables')  # just in case; will not error if file exists

# ensure column exists
existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
if "daynight" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN daynight VARCHAR')
    print("Added column daynight")
else:
    print("Column daynight exists")

# filter to existing gamePk values
existing_gamepks = set(conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_gamepks)]
print("Rows matching existing gamePk to update:", len(df))
if df.empty:
    conn.close()
    raise SystemExit(0)

# create temp table from df
conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_sched AS
SELECT CAST(gamePk AS BIGINT) AS gamePk, daynight FROM tmp_updates
""")

# update keeping existing value when API value is null
conn.execute('''
UPDATE "2025_schedule" AS s
SET daynight = COALESCE(u.daynight, s.daynight)
FROM tmp_sched u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
conn.close()

print("daynight updated for matching gamePk rows.")
