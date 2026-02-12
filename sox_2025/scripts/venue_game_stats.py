import time
import requests
import pandas as pd
import duckdb
import json
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

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

conn = duckdb.connect(DB_PATH)

# read gamePk list from DB
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

    venue = safe_get(payload, "gameData", "venue") or {}
    field_info = safe_get(venue, "fieldInfo") or {}
    location = safe_get(venue, "location") or {}
    time_zone = safe_get(venue, "timeZone") or safe_get(venue, "timeZone") or {}

    rows.append({
        "gamePk": int(safe_get(payload, "gamePk") or pk),
        "venue_id": int(safe_get(venue, "id") or None) if safe_get(venue, "id") not in (None, "") else None,
        "venue_name": safe_get(venue, "name"),
        "capacity": int(safe_get(field_info, "capacity")) if safe_get(field_info, "capacity") not in (None, "") else None,
        "turf_type": safe_get(field_info, "turfType"),
        "roof_type": safe_get(field_info, "roofType"),
        "left_line": safe_get(field_info, "leftLine"),
        "left_center": safe_get(field_info, "leftCenter"),
        "center": safe_get(field_info, "center"),
        "right_center": safe_get(field_info, "rightCenter"),
        "right_line": safe_get(field_info, "rightLine"),
        "latitude": safe_get(location, "defaultCoordinates", "latitude"),
        "longitude": safe_get(location, "defaultCoordinates", "longitude"),
        "tz_id": safe_get(venue, "timeZone", "id"),
        "tz_tz": safe_get(venue, "timeZone", "tz"),
        "venue_json": json.dumps(venue) if isinstance(venue, dict) else None
    })

    time.sleep(SLEEP_SECONDS)

if not rows:
    print("No rows fetched from API.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(rows)
# keep only gamePks that existed in schedule
existing_set = set(game_pks)
df = df[df["gamePk"].isin(existing_set)]
if df.empty:
    print("No matching rows to insert after filtering.")
    conn.close()
    raise SystemExit(0)

# create table if not exists
conn.execute("""
CREATE TABLE IF NOT EXISTS venue_game_stats (
    gamePk BIGINT,
    venue_id INTEGER,
    venue_name VARCHAR,
    capacity INTEGER,
    turf_type VARCHAR,
    roof_type VARCHAR,
    left_line INTEGER,
    left_center INTEGER,
    center INTEGER,
    right_center INTEGER,
    right_line INTEGER,
    latitude DOUBLE,
    longitude DOUBLE,
    tz_id VARCHAR,
    tz_tz VARCHAR,
    venue_json VARCHAR
)
""")

# remove existing rows for these gamePks so test runs are idempotent
gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
if gamepk_list:
    conn.execute(f"DELETE FROM venue_game_stats WHERE gamePk IN ({gamepk_list})")

# insert new rows
conn.register("tmp_venue_updates", df)
conn.execute("""
INSERT INTO venue_game_stats
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(venue_id AS INTEGER) AS venue_id,
  venue_name,
  CAST(capacity AS INTEGER) AS capacity,
  turf_type,
  roof_type,
  CAST(left_line AS INTEGER) AS left_line,
  CAST(left_center AS INTEGER) AS left_center,
  CAST(center AS INTEGER) AS center,
  CAST(right_center AS INTEGER) AS right_center,
  CAST(right_line AS INTEGER) AS right_line,
  CAST(latitude AS DOUBLE) AS latitude,
  CAST(longitude AS DOUBLE) AS longitude,
  tz_id,
  tz_tz,
  venue_json
FROM tmp_venue_updates
""")
conn.unregister("tmp_venue_updates")

print("Inserted", len(df), "rows into venue_game_stats")

conn.close()
