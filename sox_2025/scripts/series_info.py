import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"  # adjust path
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
        if pk is None:
            continue
        # extract series fields
        game_number = safe_get(game, "gameNumber")
        games_in_series = safe_get(game, "gamesInSeries")
        series_game_number = safe_get(game, "seriesGameNumber")
        rows.append({
            "gamePk": int(pk),
            "gameNumber": int(game_number) if game_number is not None else None,
            "gamesInSeries": int(games_in_series) if games_in_series is not None else None,
            "seriesGameNumber": int(series_game_number) if series_game_number is not None else None,
        })

if not rows:
    print("No rows fetched.")
    raise SystemExit(0)

df = pd.DataFrame(rows)
print("Fetched rows from API:", len(df))

conn = duckdb.connect(DB_PATH)

# ensure schedule table exists
tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
if '"2025_schedule"' not in [t if isinstance(t, str) else str(t) for t in tables] and '2025_schedule' not in tables:
    conn.close()
    raise SystemExit("Table 2025_schedule not found in DB.")

# ensure columns exist (safe)
existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
if "gameNumber" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN gameNumber INTEGER')
    print("Added column gameNumber")
if "gamesInSeries" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN gamesInSeries INTEGER')
    print("Added column gamesInSeries")
if "seriesGameNumber" not in existing_cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN seriesGameNumber INTEGER')
    print("Added column seriesGameNumber")

# filter to only gamePks that exist in DB
existing_gamepks = set(conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_gamepks)]
print("Rows matching existing gamePk to update:", len(df))
if df.empty:
    conn.close()
    raise SystemExit("No matching gamePk rows to update.")

# register DataFrame and create temp table
conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_sched AS
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(gameNumber AS INTEGER) AS gameNumber,
  CAST(gamesInSeries AS INTEGER) AS gamesInSeries,
  CAST(seriesGameNumber AS INTEGER) AS seriesGameNumber
FROM tmp_updates
""")

# update existing rows (keep existing value when incoming is null)
conn.execute('''
UPDATE "2025_schedule" AS s
SET
  gameNumber = COALESCE(u.gameNumber, s.gameNumber),
  gamesInSeries = COALESCE(u.gamesInSeries, s.gamesInSeries),
  seriesGameNumber = COALESCE(u.seriesGameNumber, s.seriesGameNumber)
FROM tmp_sched u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
conn.close()

print(f"Updated series fields for {len(df)} existing gamePk(s).")
