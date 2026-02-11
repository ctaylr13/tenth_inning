import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"  # adjust path if needed
ENDPOINT = "https://statsapi.mlb.com/api/v1/uniforms/team"
TEAM_IDS = "111"
OUT_TABLE = "redsox_uniforms"

resp = requests.get(ENDPOINT, params={"teamIds": TEAM_IDS}, timeout=30)
resp.raise_for_status()
payload = resp.json()

rows = []
for item in payload.get("uniforms", []):
    team_id = item.get("teamId")
    for ua in item.get("uniformAssets", []):
        rows.append({
            "team_id": int(team_id) if team_id is not None else None,
            "uniformAssetId": ua.get("uniformAssetId"),
            "uniformAssetCode": ua.get("uniformAssetCode"),
            "uniformAssetText": ua.get("uniformAssetText"),
            "uniformAssetTypeCode": ua.get("uniformAssetType", {}).get("uniformAssetTypeCode"),
            "uniformAssetTypeText": ua.get("uniformAssetType", {}).get("uniformAssetTypeText"),
            "uniformAssetTypeId": ua.get("uniformAssetType", {}).get("uniformAssetTypeId"),
            "active": ua.get("active"),
            "startSeason": ua.get("startSeason"),
            "endSeason": ua.get("endSeason")
        })

if not rows:
    print("No uniform rows returned.")
    raise SystemExit(0)

df = pd.DataFrame(rows)

conn = duckdb.connect(DB_PATH)

# recreate table
conn.execute(f'DROP TABLE IF EXISTS "{OUT_TABLE}"')
conn.execute(f'''
CREATE TABLE "{OUT_TABLE}" (
  team_id INTEGER,
  uniformAssetId INTEGER,
  uniformAssetCode VARCHAR,
  uniformAssetText VARCHAR,
  uniformAssetTypeCode VARCHAR,
  uniformAssetTypeText VARCHAR,
  uniformAssetTypeId INTEGER,
  active BOOLEAN,
  startSeason VARCHAR,
  endSeason VARCHAR
)
''')

conn.register("tmp_df", df)
conn.execute(f'INSERT INTO "{OUT_TABLE}" SELECT * FROM tmp_df')
conn.unregister("tmp_df")
conn.close()

print(f"Wrote {len(df)} rows to {OUT_TABLE}.")
