import time
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, List, Optional
from tqdm import tqdm

DB_PATH = "../../redsox_25.duckdb"
UNIFORMS_URL = "https://statsapi.mlb.com/api/v1/uniforms/game"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
BATCH_SIZE = 50
USER_AGENT = "tenth-inning-uniforms/1.0"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def extract_jersey(side_obj: Optional[Dict[str, Any]]):
    if not side_obj:
        return None, None
    for asset in side_obj.get("uniformAssets", []) or []:
        atype = safe_get(asset, "uniformAssetType", "uniformAssetTypeId")
        if atype == 1:  # jersey
            return asset.get("uniformAssetId"), asset.get("uniformAssetText")
    return None, None


def ensure_columns(conn):
    existing = {r[1] for r in conn.execute("PRAGMA table_info('2025_schedule')").fetchall()}
    to_add = [
        ("home_team_jersey_id", "INTEGER"),
        ("home_team_jersey_text", "VARCHAR"),
        ("away_team_jersey_id", "INTEGER"),
        ("away_team_jersey_text", "VARCHAR"),
    ]
    for name, ctype in to_add:
        if name not in existing:
            conn.execute(f'ALTER TABLE "2025_schedule" ADD COLUMN {name} {ctype}')


def main():
    conn = duckdb.connect(DB_PATH)
    try:
        # Get gamePks
        df_g = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
        if df_g.empty:
            print("No gamePks found.")
            return
        game_pks = df_g["gamePk"].astype(int).tolist()
        print("Found", len(game_pks), "gamePks")

        ensure_columns(conn)

        # Process gamePks in batches
        batches = [game_pks[i:i + BATCH_SIZE] for i in range(0, len(game_pks), BATCH_SIZE)]
        rows: List[Dict[str, Any]] = []

        for batch in tqdm(batches, desc="batches"):
            params = {"gamePks": ",".join(map(str, batch))}
            try:
                r = session.get(UNIFORMS_URL, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                payload = r.json()
            except Exception as e:
                print(f"Fetch error for batch {batch[0]}-{batch[-1]}: {e}")
                time.sleep(SLEEP_SECONDS)
                continue

            for entry in payload.get("uniforms", []) or []:
                pk = entry.get("gamePk")
                home_obj = entry.get("home")
                away_obj = entry.get("away")
                home_id, home_text = extract_jersey(home_obj)
                away_id, away_text = extract_jersey(away_obj)
                rows.append({
                    "gamePk": int(pk),
                    "home_team_jersey_id": int(home_id) if home_id is not None else None,
                    "home_team_jersey_text": home_text,
                    "away_team_jersey_id": int(away_id) if away_id is not None else None,
                    "away_team_jersey_text": away_text,
                })
            time.sleep(SLEEP_SECONDS)

        if not rows:
            print("No jersey rows extracted.")
            return

        # Create DataFrame and filter rows
        df = pd.DataFrame(rows)
        existing_set = set(game_pks)
        df = df[df["gamePk"].isin(existing_set)]
        if df.empty:
            print("No rows to update after filtering.")
            return

        # Update database
        conn.register("tmp_jers", df)
        conn.execute("""
        CREATE TEMPORARY TABLE tmp_jerseys AS
        SELECT CAST(gamePk AS BIGINT) AS gamePk,
               CAST(home_team_jersey_id AS INTEGER) AS home_team_jersey_id,
               home_team_jersey_text,
               CAST(away_team_jersey_id AS INTEGER) AS away_team_jersey_id,
               away_team_jersey_text
        FROM tmp_jers
        """)

        conn.execute('''
        UPDATE "2025_schedule" AS s
        SET
            home_team_jersey_id = COALESCE(t.home_team_jersey_id, s.home_team_jersey_id),
            home_team_jersey_text = COALESCE(t.home_team_jersey_text, s.home_team_jersey_text),
            away_team_jersey_id = COALESCE(t.away_team_jersey_id, s.away_team_jersey_id),
            away_team_jersey_text = COALESCE(t.away_team_jersey_text, s.away_team_jersey_text)
        FROM tmp_jerseys t
        WHERE s.gamePk = t.gamePk
        ''')

        conn.unregister("tmp_jers")
        conn.execute("DROP TABLE IF EXISTS tmp_jerseys")
        print("Updated jersey columns for", len(df), "games")
    finally:
        conn.close()


main()