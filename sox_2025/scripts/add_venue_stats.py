import time
import requests
import pandas as pd
import duckdb
import json
from typing import Dict, Any

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
    time_zone = safe_get(venue, "timeZone") or {}
    weather = safe_get(payload, "gameData", "weather") or {}
    game_info = safe_get(payload, "gameData", "gameInfo") or {}

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
        "azimuth_angle": safe_get(location, "azimuthAngle"),
        "elevation": safe_get(location, "elevation"),
        "tz_id": safe_get(time_zone, "id"),
        "tz_tz": safe_get(time_zone, "tz"),
        "weather_condition": safe_get(weather, "condition"),
        "weather_temp": safe_get(weather, "temp"),
        "weather_wind": safe_get(weather, "wind"),
        "attendance": safe_get(game_info, "attendance"),
        "first_pitch": safe_get(game_info, "firstPitch"),
        "game_duration_minutes": safe_get(game_info, "gameDurationMinutes"),
        "venue_json": json.dumps(venue) if isinstance(venue, dict) else None
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
    azimuth_angle DOUBLE,
    elevation DOUBLE,
    tz_id VARCHAR,
    tz_tz VARCHAR,
    weather_condition VARCHAR,
    weather_temp VARCHAR,
    weather_wind VARCHAR,
    attendance INTEGER,
    first_pitch TIMESTAMP,
    game_duration_minutes INTEGER,
    venue_json VARCHAR
)
""")

gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
if gamepk_list:
    conn.execute(f"DELETE FROM venue_game_stats WHERE gamePk IN ({gamepk_list})")

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
  CAST(azimuth_angle AS DOUBLE) AS azimuth_angle,
  CAST(elevation AS DOUBLE) AS elevation,
  tz_id,
  tz_tz,
  weather_condition,
  weather_temp,
  weather_wind,
  CAST(attendance AS INTEGER) AS attendance,
  TRY_CAST(first_pitch AS TIMESTAMP) AS first_pitch,
  CAST(game_duration_minutes AS INTEGER) AS game_duration_minutes,
  venue_json
FROM tmp_venue_updates
""")
conn.unregister("tmp_venue_updates")

print("Inserted", len(df), "rows into venue_game_stats")
conn.close()
