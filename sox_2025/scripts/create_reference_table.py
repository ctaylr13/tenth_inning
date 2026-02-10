import requests
import pandas as pd
import duckdb
from typing import Any, Dict

DB_PATH = "../../redsox_25.duckdb"
ENDPOINT = "https://statsapi.mlb.com/api/v1/teams"
PARAMS = {"sportId": 1}  # only MLB teams

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

resp = requests.get(ENDPOINT, params=PARAMS, timeout=30)
resp.raise_for_status()
payload = resp.json()

rows = []
for team in payload.get("teams", []):
    rows.append({
        "springLeague_id": safe_get(team, "springLeague", "id"),
        "springLeague_abbr": safe_get(team, "springLeague", "abbreviation"),
        "team_id": safe_get(team, "id"),
        "team_name": safe_get(team, "name"),
        "venue_id": safe_get(team, "venue", "id"),
        "venue_name": safe_get(team, "venue", "name"),
        "springVenue_id": safe_get(team, "springVenue", "id"),
        "teamCode": safe_get(team, "teamCode"),
        "abbreviation": safe_get(team, "abbreviation"),
        "teamName": safe_get(team, "teamName"),
        "locationName": safe_get(team, "locationName"),
        "league_id": safe_get(team, "league", "id"),
        "division_id": safe_get(team, "division", "id"),
        "shortName": safe_get(team, "shortName"),
        "franchiseName": safe_get(team, "franchiseName"),
        "clubName": safe_get(team, "clubName"),
        "active": safe_get(team, "active"),
    })

if not rows:
    print("No teams returned.")
    raise SystemExit(0)

df = pd.DataFrame(rows)

conn = duckdb.connect(DB_PATH)

conn.execute('''
CREATE TABLE IF NOT EXISTS teams_reference (
    springLeague_id INTEGER,
    springLeague_abbr VARCHAR,
    team_id INTEGER,
    team_name VARCHAR,
    venue_id INTEGER,
    venue_name VARCHAR,
    springVenue_id INTEGER,
    teamCode VARCHAR,
    abbreviation VARCHAR,
    teamName VARCHAR,
    locationName VARCHAR,
    league_id INTEGER,
    division_id INTEGER,
    shortName VARCHAR,
    franchiseName VARCHAR,
    clubName VARCHAR,
    active BOOLEAN
)
''')

# Replace existing table contents (simple approach)
conn.execute('DROP TABLE IF EXISTS teams_reference')
conn.register("tmp_df", df)
conn.execute('CREATE TABLE teams_reference AS SELECT * FROM tmp_df')
conn.unregister("tmp_df")

conn.close()
print(f"Wrote {len(df)} teams to teams_reference.")
