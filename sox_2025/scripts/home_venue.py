import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"  # adjust path if needed
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

# Fetch schedule (teams hydrated)
params = {
    "hydrate": HYDRATE,
    "sportId": SPORT_ID,
    "startDate": START_DATE,
    "endDate": END_DATE,
}
resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
resp.raise_for_status()
payload = resp.json()

# Build list of (gamePk, home_venue_id) rows
rows = []
for date_block in payload.get("dates", []):
    for game in date_block.get("games", []):
        pk = game.get("gamePk")
        home_venue_id = safe_get(game, "teams", "home", "team", "venue", "id")
        if pk is not None:
            rows.append({
                "gamePk": int(pk),
                "home_venue_id": int(home_venue_id) if home_venue_id is not None else None
            })

if not rows:
    print("No rows fetched from API.")
    raise SystemExit(0)

df = pd.DataFrame(rows)
print("Fetched rows from API:", len(df))

conn = duckdb.connect(DB_PATH)

# ensure schedule table exists
tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
if '"2025_schedule"' not in [t if isinstance(t, str) else str(t) for t in tables] and '2025_schedule' not in tables:
    raise SystemExit("Table 2025_schedule not found in DB.")

# ensure home_venue_id column exists
existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
if "home_venue_id" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN home_venue_id BIGINT')
    print("Added column home_venue_id")
else:
    print("Column home_venue_id already exists")

# filter to only gamePks that exist in DB to avoid creating new rows
existing_gamepks = set(conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_gamepks)]
print("Rows matching existing gamePk to update:", len(df))
if df.empty:
    print("No matching gamePk rows to update.")
    conn.close()
    raise SystemExit(0)

# register DataFrame and create temporary table
conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_sched AS
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(home_venue_id AS BIGINT) AS home_venue_id
FROM tmp_updates
""")

# preview (optional; uncomment to inspect)
# print(conn.execute("SELECT gamePk, home_venue_id FROM tmp_sched LIMIT 20").fetchdf())

# update only when tmp value is not null, otherwise keep existing
conn.execute('''
UPDATE "2025_schedule" AS s
SET home_venue_id = COALESCE(u.home_venue_id, s.home_venue_id)
FROM tmp_sched u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
conn.close()

print(f"Updated home_venue_id for {len(df)} existing gamePk(s).")
