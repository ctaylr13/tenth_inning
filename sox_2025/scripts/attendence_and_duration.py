import time
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"   # adjust to your path
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
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

# read gamePk list from DB
existing = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
game_pks = existing["gamePk"].astype(int).tolist()
print("Found", len(game_pks), "gamePk(s) in DB")

# ensure columns exist
cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
if "attendance" not in cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN attendance INTEGER')
    print("Added column attendance")
if "gameDurationMinutes" not in cols:
    conn.execute('ALTER TABLE "2025_schedule" ADD COLUMN gameDurationMinutes INTEGER')
    print("Added column gameDurationMinutes")

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

    game_info = safe_get(payload, "gameData", "gameInfo") or safe_get(payload, "game", "gameInfo") or safe_get(payload, "gameData", "game", "gameInfo")
    attendance = safe_get(game_info or {}, "attendance")
    duration = safe_get(game_info or {}, "gameDurationMinutes")

    rows.append({
        "gamePk": int(pk),
        "attendance": int(attendance) if attendance not in (None, "") else None,
        "gameDurationMinutes": int(duration) if duration not in (None, "") else None,
    })

    time.sleep(SLEEP_SECONDS)

# update DB
if rows:
    df = pd.DataFrame(rows)
    # keep only existing gamePk (should be)
    existing_set = set(game_pks)
    df = df[df["gamePk"].isin(existing_set)]
    if not df.empty:
        conn.register("tmp_updates", df)
        conn.execute("""
        CREATE TEMPORARY TABLE tmp_sched AS
        SELECT CAST(gamePk AS BIGINT) AS gamePk,
               CAST(attendance AS INTEGER) AS attendance,
               CAST(gameDurationMinutes AS INTEGER) AS gameDurationMinutes
        FROM tmp_updates
        """)
        conn.execute('''
        UPDATE "2025_schedule" AS s
        SET attendance = COALESCE(u.attendance, s.attendance),
            gameDurationMinutes = COALESCE(u.gameDurationMinutes, s.gameDurationMinutes)
        FROM tmp_sched u
        WHERE s.gamePk = u.gamePk
        ''')
        conn.unregister("tmp_updates")
        print("Updated", len(df), "rows")
    else:
        print("No matching rows to update after filtering.")
else:
    print("No rows fetched from API.")

conn.close()
