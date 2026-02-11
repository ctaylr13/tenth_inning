import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"   # adjust to your path
BASE_URL = "https://statsapi.mlb.com/api/v1/schedule"
HYDRATE = "team"
SPORT_ID = 1
START_DATE = "2025-03-27"
END_DATE = "2025-09-30"

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
resp = requests.get(BASE_URL, params=params, timeout=60)
resp.raise_for_status()
payload = resp.json()

rows = []
for date_block in payload.get("dates", []):
    for game in date_block.get("games", []):
        pk = game.get("gamePk")
        home_id = safe_get(game, "teams", "home", "team", "id")
        home_team_venue_id = safe_get(game, "teams", "home", "team", "venue", "id")
        if pk is not None:
            rows.append({
                "gamePk": int(pk),
                "home_team_id": int(home_id) if home_id is not None else None,
                "home_team_venue_id": int(home_team_venue_id) if home_team_venue_id is not None else None
            })

if not rows:
    print("No rows fetched.")
    raise SystemExit(0)

df = pd.DataFrame(rows)
print("Fetched rows:", len(df))

conn = duckdb.connect(DB_PATH)

# Diagnostic
print("SHOW TABLES:", conn.execute("SHOW TABLES").fetchdf())
print('PRAGMA table_info("2025_schedule"):')
print(conn.execute('PRAGMA table_info("2025_schedule")').fetchdf())

# ensure columns exist (safe)
existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
if "home_team_id" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN home_team_id BIGINT')
    print("Added column home_team_id")
else:
    print("Column home_team_id exists")

if "home_venue_id" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN home_venue_id BIGINT')
    print("Added column home_venue_id")
else:
    print("Column home_venue_id exists")

# filter to existing gamePk values to avoid affecting non-existent rows
existing_gamepks = set(conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_gamepks)]
print("Matched existing gamePk rows to update:", len(df))
if df.empty:
    print("No matching existing gamePk rows to update.")
    conn.close()
    raise SystemExit(0)

# register DataFrame and create temporary table mapping API field -> DB column (home_team_venue_id -> home_venue_id)
conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_sched AS
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(home_team_id AS BIGINT) AS home_team_id,
  CAST(home_team_venue_id AS BIGINT) AS home_venue_id
FROM tmp_updates
""")

# update both home_team_id and home_venue_id from temp table
conn.execute('''
UPDATE "2025_schedule" AS s
SET
  home_team_id = u.home_team_id,
  home_venue_id = u.home_venue_id
FROM tmp_sched u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
conn.close()

print(f"Updated home_team_id and home_venue_id for {len(df)} existing gamePk(s).")
