import time
import requests
import pandas as pd
import duckdb
from typing import Dict, Any, Optional

DB_PATH = "../../redsox_25.duckdb"   # adjust if needed
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
USER_AGENT = "tenth-inning-script/1.0 (+you@example.com)"

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

# read gamePk list
df_games = conn.execute('SELECT DISTINCT gamePk FROM redsox_25.main."2025_schedule"').fetchdf()
game_pks = df_games["gamePk"].astype(int).tolist()
print("Found", len(game_pks), "gamePk(s)")

rows = []
total = len(game_pks)
for i, pk in enumerate(game_pks, start=1):
    try:
        r = session.get(GAME_URL.format(pk=pk), timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[{i}/{total}] {pk} - fetch error: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    home_rec = safe_get(payload, "gameData", "teams", "home", "record") or {}
    away_rec = safe_get(payload, "gameData", "teams", "away", "record") or {}

    rows.append({
        "gamePk": int(pk),
        "home_gamesPlayed": safe_get(home_rec, "gamesPlayed"),
        "home_divisionLeader": safe_get(home_rec, "divisionLeader"),
        "home_wins": safe_get(home_rec, "wins"),
        "home_losses": safe_get(home_rec, "losses"),
        "home_winningPercentage": safe_get(home_rec, "winningPercentage"),
        "away_gamesPlayed": safe_get(away_rec, "gamesPlayed"),
        "away_divisionLeader": safe_get(away_rec, "divisionLeader"),
        "away_wins": safe_get(away_rec, "wins"),
        "away_losses": safe_get(away_rec, "losses"),
        "away_winningPercentage": safe_get(away_rec, "winningPercentage"),
    })

    print(f"[{i}/{total}] {pk} collected")
    time.sleep(SLEEP_SECONDS)

if not rows:
    print("No rows collected.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(rows)

# add columns to schedule table if missing
cols = [r[0] for r in conn.execute('PRAGMA table_info(redsox_25.main."2025_schedule")').fetchall()]
to_add = []
for c in [
    ("home_gamesPlayed", "INTEGER"),
    ("home_divisionLeader", "BOOLEAN"),
    ("home_wins", "INTEGER"),
    ("home_losses", "INTEGER"),
    ("home_winningPercentage", "VARCHAR"),
    ("away_gamesPlayed", "INTEGER"),
    ("away_divisionLeader", "BOOLEAN"),
    ("away_wins", "INTEGER"),
    ("away_losses", "INTEGER"),
    ("away_winningPercentage", "VARCHAR"),
]:
    if c[0] not in cols:
        conn.execute(f'ALTER TABLE redsox_25.main."2025_schedule" ADD COLUMN {c[0]} {c[1]}')
        print("Added column", c[0])

# delete existing rows for these gamePks then update via tmp table
existing_set = set(conn.execute('SELECT DISTINCT gamePk FROM redsox_25.main."2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_set)]
if df.empty:
    print("No matching schedule rows to update after filtering.")
    conn.close()
    raise SystemExit(0)

conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_rec AS
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(home_gamesPlayed AS INTEGER) AS home_gamesPlayed,
  CAST(home_divisionLeader AS BOOLEAN) AS home_divisionLeader,
  CAST(home_wins AS INTEGER) AS home_wins,
  CAST(home_losses AS INTEGER) AS home_losses,
  home_winningPercentage,
  CAST(away_gamesPlayed AS INTEGER) AS away_gamesPlayed,
  CAST(away_divisionLeader AS BOOLEAN) AS away_divisionLeader,
  CAST(away_wins AS INTEGER) AS away_wins,
  CAST(away_losses AS INTEGER) AS away_losses,
  away_winningPercentage
FROM tmp_updates
""")

conn.execute('''
UPDATE redsox_25.main."2025_schedule" AS s
SET
  home_gamesPlayed = COALESCE(u.home_gamesPlayed, s.home_gamesPlayed),
  home_divisionLeader = COALESCE(u.home_divisionLeader, s.home_divisionLeader),
  home_wins = COALESCE(u.home_wins, s.home_wins),
  home_losses = COALESCE(u.home_losses, s.home_losses),
  home_winningPercentage = COALESCE(u.home_winningPercentage, s.home_winningPercentage),
  away_gamesPlayed = COALESCE(u.away_gamesPlayed, s.away_gamesPlayed),
  away_divisionLeader = COALESCE(u.away_divisionLeader, s.away_divisionLeader),
  away_wins = COALESCE(u.away_wins, s.away_wins),
  away_losses = COALESCE(u.away_losses, s.away_losses),
  away_winningPercentage = COALESCE(u.away_winningPercentage, s.away_winningPercentage)
FROM tmp_rec u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
print("Updated", len(df), "schedule rows with team records.")
conn.close()
