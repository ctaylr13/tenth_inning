import time
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, List
from tqdm import tqdm

DB_PATH = "../../redsox_25.duckdb"   # adjust
UNIFORMS_URL = "https://statsapi.mlb.com/api/v1/uniforms/game"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
SOX_TEAM_ID = 111
USER_AGENT = "tenth-inning-uniforms/1.0"
BATCH_SIZE = 50

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

# collect gamePks from DB
existing = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
game_pks = existing["gamePk"].astype(int).tolist()
print("Found", len(game_pks), "gamePk(s) in DB")



# ensure columns exist (safe)
existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
for col_name, col_sql in [
    ("hat_asset_id", 'ALTER TABLE "2025_schedule" ADD COLUMN hat_asset_id INTEGER'),
    ("jersey_asset_id", 'ALTER TABLE "2025_schedule" ADD COLUMN jersey_asset_id INTEGER'),
    ("pants_asset_id", 'ALTER TABLE "2025_schedule" ADD COLUMN pants_asset_id INTEGER'),
]:
    if col_name not in existing_cols:
        try:
            conn.execute(col_sql)
            print("Added column", col_name)
            existing_cols.append(col_name)
        except Exception:
            # ignore if another process created it concurrently
            pass


# mapping asset type id -> column name
TYPE_TO_COL = {1: "jersey_asset_id", 2: "pants_asset_id", 3: "hat_asset_id"}

def process_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for entry in payload.get("uniforms", []):
        pk = entry.get("gamePk")
        hat_id = jersey_id = pants_id = None
        # check home and away sections for Sox
        for side in ("home", "away"):
            side_obj = entry.get(side)
            if not side_obj:
                continue
            team_id = side_obj.get("id")
            if int(team_id) != SOX_TEAM_ID:
                continue
            for asset in side_obj.get("uniformAssets", []):
                aid = asset.get("uniformAssetId")
                at = safe_get(asset, "uniformAssetType", "uniformAssetTypeId")
                col = TYPE_TO_COL.get(at)
                if not col:
                    continue
                # pick first found per type
                if col == "hat_asset_id" and hat_id is None:
                    hat_id = aid
                elif col == "jersey_asset_id" and jersey_id is None:
                    jersey_id = aid
                elif col == "pants_asset_id" and pants_id is None:
                    pants_id = aid
        rows.append({
            "gamePk": int(pk),
            "hat_asset_id": int(hat_id) if hat_id is not None else None,
            "jersey_asset_id": int(jersey_id) if jersey_id is not None else None,
            "pants_asset_id": int(pants_id) if pants_id is not None else None,
        })
    return rows

# batch and update
batches = [game_pks[i:i+BATCH_SIZE] for i in range(0, len(game_pks), BATCH_SIZE)]
total_updated = 0

for batch in tqdm(batches, desc="batches"):
    params = {"gamePks": ",".join(map(str, batch))}
    try:
        r = session.get(UNIFORMS_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"Batch {batch[0]}-{batch[-1]} fetch error: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    rows = process_payload(payload)
    if not rows:
        print(f"Batch {batch[0]}-{batch[-1]} no uniform rows")
        time.sleep(SLEEP_SECONDS)
        continue

    df = pd.DataFrame(rows)
    # filter to only existing gamePks (safety)
    existing_set = set(game_pks)
    df = df[df["gamePk"].isin(existing_set)]
    if df.empty:
        time.sleep(SLEEP_SECONDS)
        continue
    

    # single DB update per batch
     # single DB update per batch
    conn.register("tmp_updates", df)
    # drop any previous temp table
    conn.execute('DROP TABLE IF EXISTS tmp_uniforms')
    conn.execute("""
    CREATE TEMPORARY TABLE tmp_uniforms AS
    SELECT CAST(gamePk AS BIGINT) AS gamePk,
           CAST(hat_asset_id AS INTEGER) AS hat_asset_id,
           CAST(jersey_asset_id AS INTEGER) AS jersey_asset_id,
           CAST(pants_asset_id AS INTEGER) AS pants_asset_id
    FROM tmp_updates
    """)
    conn.execute('''
    UPDATE "2025_schedule" AS s
    SET
      hat_asset_id = COALESCE(u.hat_asset_id, s.hat_asset_id),
      jersey_asset_id = COALESCE(u.jersey_asset_id, s.jersey_asset_id),
      pants_asset_id = COALESCE(u.pants_asset_id, s.pants_asset_id)
    FROM tmp_uniforms u
    WHERE s.gamePk = u.gamePk
    ''')
    conn.unregister("tmp_updates")
    # drop temp table to avoid conflicts next batch
    conn.execute('DROP TABLE IF EXISTS tmp_uniforms')

    total_updated += len(df)
    print(f"Batch updated {len(df)} games ({batch[0]}-{batch[-1]})")
    time.sleep(SLEEP_SECONDS)

conn.close()
print("Done. Total updated:", total_updated)
