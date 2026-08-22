import time
import requests
import json
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
HEADERS = {"User-Agent": "tenth-inning-script/1.0 (6282920+ctaylr13@users.noreply.github.com)"}
TIMEOUT = 30
SLEEP_SECONDS = 0.1
# LIMIT = 10  # number of gamePks to test/write

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

def main():
    conn = duckdb.connect(DB_PATH)
    try:
        df = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule" ORDER BY gamePk ').fetchdf()
        game_pks = df["gamePk"].astype(int).tolist()
        print(f"Found {len(game_pks)} gamePk(s) to fetch")
    finally:
        conn.close()
    session = requests.Session()
    session.headers.update(HEADERS)

    rows = []
    fetched = 0
    failures = 0
    for i, pk in enumerate(game_pks, start=1):
        print(f"[{i}/{len(game_pks)}] Fetching gamePk {pk}...", end=" ")
        try:
            r = session.get(GAME_URL.format(pk=pk), timeout=TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            fetched += 1
            print("OK")
        except Exception as e:
            failures += 1
            print(f"FAILED: {e}")
            time.sleep(SLEEP_SECONDS)
            continue

        dec = safe_get(payload, "liveData", "decisions") or {}
        winner = safe_get(dec, "winner", "id")
        loser = safe_get(dec, "loser", "id")
        save = safe_get(dec, "save", "id")

        print(f"  decisions -> winner: {winner}, loser: {loser}, save: {save}")

        rows.append({
            "gamePk": int(safe_get(payload, "gamePk") or pk),
            "winner_id": int(winner) if winner is not None else None,
            "loser_id": int(loser) if loser is not None else None,
            "save_id": int(save) if save is not None else None,
        })

        time.sleep(SLEEP_SECONDS)

    print(f"Fetch summary: fetched={fetched}, failures={failures}, rows_collected={len(rows)}")
    if not rows:
        print("No rows to write. Exiting.")
        return

    df_rows = pd.DataFrame(rows)

    conn = duckdb.connect(DB_PATH)
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS game_decisions (
            gamePk BIGINT PRIMARY KEY,
            winner_id INTEGER,
            loser_id INTEGER,
            save_id INTEGER
        )
        """)
        # delete existing for these gamePks
        gp_list = ",".join(str(int(x)) for x in sorted(df_rows["gamePk"].unique()))
        if gp_list:
            print("Deleting existing rows for gamePks:", gp_list)
            conn.execute(f"DELETE FROM game_decisions WHERE gamePk IN ({gp_list})")

        conn.register("tmp_dec", df_rows)
        conn.execute("""
        INSERT INTO game_decisions
        SELECT
        CAST(gamePk AS BIGINT) AS gamePk,
        CAST(winner_id AS INTEGER) AS winner_id,
        CAST(loser_id AS INTEGER) AS loser_id,
        CAST(save_id AS INTEGER) AS save_id
        FROM tmp_dec
        """)
        conn.unregister("tmp_dec")

        print(f"Inserted/updated {len(df_rows)} rows into game_decisions")
    finally:
        conn.close()


main()