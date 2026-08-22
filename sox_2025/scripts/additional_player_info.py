import math
import time
import json
import requests
import pandas as pd
import duckdb
from typing import List, Dict, Any, Optional
from tqdm import tqdm

DB_PATH = "../../redsox_25.duckdb"
PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
BATCH_SIZE = 50
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

# collect distinct playerIds
df_ids = conn.execute("""
SELECT DISTINCT playerId
FROM redsox_25.main.game_rosters
WHERE playerId IS NOT NULL
""").fetchdf()

player_ids = sorted({int(x) for x in df_ids["playerId"].tolist()})
if not player_ids:
    print("No playerIds found in game_rosters.")
    conn.close()
    raise SystemExit(0)

# prepare batches
batches = [player_ids[i:i+BATCH_SIZE] for i in range(0, len(player_ids), BATCH_SIZE)]
print(f"Found {len(player_ids)} playerIds, {len(batches)} batch(es) of up to {BATCH_SIZE}.")

all_rows = []

for batch in tqdm(batches, desc="Fetching player batches", unit="batch"):
    ids_str = ",".join(str(x) for x in batch)
    params = {"personIds": ids_str}
    try:
        r = session.get(PEOPLE_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"Fetch error for batch starting with {batch[0]}: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    people = payload.get("people", []) or []
    for p in people:
        pid = safe_get(p, "id")
        row = {
            "playerId": int(pid) if pid is not None else None,
            "fullName": safe_get(p, "fullName"),
            "firstName": safe_get(p, "firstName"),
            "lastName": safe_get(p, "lastName"),
            "primaryNumber": safe_get(p, "primaryNumber"),
            "birthDate": safe_get(p, "birthDate"),
            "currentAge": safe_get(p, "currentAge"),
            "birthCity": safe_get(p, "birthCity"),
            "birthStateProvince": safe_get(p, "birthStateProvince"),
            "birthCountry": safe_get(p, "birthCountry"),
            "height": safe_get(p, "height"),
            "weight": safe_get(p, "weight"),
            "active": safe_get(p, "active"),
            "primaryPosition_code": safe_get(p, "primaryPosition", "code"),
            "primaryPosition_name": safe_get(p, "primaryPosition", "name"),
            "primaryPosition_type": safe_get(p, "primaryPosition", "type"),
            "primaryPosition_abbreviation": safe_get(p, "primaryPosition", "abbreviation"),
            "draftYear": safe_get(p, "draftYear"),
            "mlbDebutDate": safe_get(p, "mlbDebutDate"),
            "batSide_code": safe_get(p, "batSide", "code"),
            "batSide_description": safe_get(p, "batSide", "description"),
            "pitchHand_code": safe_get(p, "pitchHand", "code"),
            "pitchHand_description": safe_get(p, "pitchHand", "description"),
            "strikeZoneTop": safe_get(p, "strikeZoneTop"),
            "strikeZoneBottom": safe_get(p, "strikeZoneBottom")
        }
        all_rows.append(row)

    time.sleep(SLEEP_SECONDS)

if not all_rows:
    print("No player data fetched.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(all_rows)

# create table if missing
conn.execute("""
CREATE TABLE IF NOT EXISTS redsox_25.main.player_reference (
  playerId INTEGER PRIMARY KEY,
  fullName VARCHAR,
  firstName VARCHAR,
  lastName VARCHAR,
  primaryNumber VARCHAR,
  birthDate VARCHAR,
  currentAge INTEGER,
  birthCity VARCHAR,
  birthStateProvince VARCHAR,
  birthCountry VARCHAR,
  height VARCHAR,
  weight INTEGER,
  active BOOLEAN,
  primaryPosition_code VARCHAR,
  primaryPosition_name VARCHAR,
  primaryPosition_type VARCHAR,
  primaryPosition_abbreviation VARCHAR,
  draftYear INTEGER,
  mlbDebutDate VARCHAR,
  batSide_code VARCHAR,
  batSide_description VARCHAR,
  pitchHand_code VARCHAR,
  pitchHand_description VARCHAR,
  strikeZoneTop DOUBLE,
  strikeZoneBottom DOUBLE
)
""")

# upsert: delete any existing rows for these playerIds then insert
unique_ids = sorted(df["playerId"].dropna().astype(int).unique().tolist())
if unique_ids:
    ids_list = ",".join(str(x) for x in unique_ids)
    conn.execute(f"DELETE FROM redsox_25.main.player_reference WHERE playerId IN ({ids_list})")

conn.register("tmp_players", df)
conn.execute("""
INSERT INTO redsox_25.main.player_reference
SELECT
  CAST(playerId AS INTEGER) AS playerId,
  fullName,
  firstName,
  lastName,
  primaryNumber,
  birthDate,
  TRY_CAST(currentAge AS INTEGER) AS currentAge,
  birthCity,
  birthStateProvince,
  birthCountry,
  height,
  TRY_CAST(weight AS INTEGER) AS weight,
  TRY_CAST(active AS BOOLEAN) AS active,
  primaryPosition_code,
  primaryPosition_name,
  primaryPosition_type,
  primaryPosition_abbreviation,
  TRY_CAST(draftYear AS INTEGER) AS draftYear,
  mlbDebutDate,
  batSide_code,
  batSide_description,
  pitchHand_code,
  pitchHand_description,
  TRY_CAST(strikeZoneTop AS DOUBLE) AS strikeZoneTop,
  TRY_CAST(strikeZoneBottom AS DOUBLE) AS strikeZoneBottom
FROM tmp_players
""")
conn.unregister("tmp_players")

print(f"Inserted/updated {len(df)} people into player_reference")
conn.close()
