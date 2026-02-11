import requests
import pandas as pd
import duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"  # adjust as needed
BASE_URL = "https://statsapi.mlb.com/api/v1/schedule"
HYDRATE = "team"
SPORT_ID = 1
START_DATE = "2025-03-27"
END_DATE = "2025-09-30"
SOX_TEAM_ID = 111
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

params = {"hydrate": HYDRATE, "sportId": SPORT_ID, "startDate": START_DATE, "endDate": END_DATE}
resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
resp.raise_for_status()
payload = resp.json()

rows = []
for date_block in payload.get("dates", []):
    for game in date_block.get("games", []):
        pk = game.get("gamePk")
        if pk is None:
            continue

        home_score = safe_get(game, "teams", "home", "score")
        away_score = safe_get(game, "teams", "away", "score")
        home_is_winner = safe_get(game, "teams", "home", "isWinner")
        away_is_winner = safe_get(game, "teams", "away", "isWinner")

        home_team_id = safe_get(game, "teams", "home", "team", "id")
        away_team_id = safe_get(game, "teams", "away", "team", "id")

        if home_team_id == SOX_TEAM_ID:
            sox_is_winner = bool(home_is_winner)
            sox_wins = safe_get(game, "teams", "home", "leagueRecord", "wins")
            sox_losses = safe_get(game, "teams", "home", "leagueRecord", "losses")
            sox_pct = safe_get(game, "teams", "home", "leagueRecord", "pct")
        elif away_team_id == SOX_TEAM_ID:
            sox_is_winner = bool(away_is_winner)
            sox_wins = safe_get(game, "teams", "away", "leagueRecord", "wins")
            sox_losses = safe_get(game, "teams", "away", "leagueRecord", "losses")
            sox_pct = safe_get(game, "teams", "away", "leagueRecord", "pct")
        else:
            sox_is_winner = None
            sox_wins = None
            sox_losses = None
            sox_pct = None

        rows.append({
            "gamePk": int(pk),
            "home_score": int(home_score) if home_score is not None else None,
            "away_score": int(away_score) if away_score is not None else None,
            "sox_is_winner": bool(sox_is_winner) if sox_is_winner is not None else None,
            "sox_wins": int(sox_wins) if sox_wins is not None else None,
            "sox_losses": int(sox_losses) if sox_losses is not None else None,
            "sox_pct": str(sox_pct) if sox_pct is not None else None,
        })

if not rows:
    print("No rows fetched.")
    raise SystemExit(0)

df = pd.DataFrame(rows)
print("Fetched rows:", len(df))

conn = duckdb.connect(DB_PATH)

existing_cols = [r[0] for r in conn.execute('PRAGMA table_info("2025_schedule")').fetchall()]
alter_sql = []
if "home_score" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN home_score INTEGER')
if "away_score" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN away_score INTEGER')
if "sox_is_winner" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN sox_is_winner BOOLEAN')
if "sox_wins" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN sox_wins INTEGER')
if "sox_losses" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN sox_losses INTEGER')
if "sox_pct" not in existing_cols:
    alter_sql.append('ALTER TABLE "2025_schedule" ADD COLUMN sox_pct VARCHAR')

for sql in alter_sql:
    conn.execute(sql)

existing_gamepks = set(conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist())
df = df[df["gamePk"].isin(existing_gamepks)]
print("Rows matching existing gamePk to update:", len(df))
if df.empty:
    conn.close()
    raise SystemExit(0)

conn.register("tmp_updates", df)
conn.execute("""
CREATE TEMPORARY TABLE tmp_sched AS
SELECT
  CAST(gamePk AS BIGINT) AS gamePk,
  CAST(home_score AS INTEGER) AS home_score,
  CAST(away_score AS INTEGER) AS away_score,
  CAST(sox_is_winner AS BOOLEAN) AS sox_is_winner,
  CAST(sox_wins AS INTEGER) AS sox_wins,
  CAST(sox_losses AS INTEGER) AS sox_losses,
  sox_pct
FROM tmp_updates
""")

conn.execute('''
UPDATE "2025_schedule" AS s
SET
  home_score = COALESCE(u.home_score, s.home_score),
  away_score = COALESCE(u.away_score, s.away_score),
  sox_is_winner = COALESCE(u.sox_is_winner, s.sox_is_winner),
  sox_wins = COALESCE(u.sox_wins, s.sox_wins),
  sox_losses = COALESCE(u.sox_losses, s.sox_losses),
  sox_pct = COALESCE(u.sox_pct, s.sox_pct)
FROM tmp_sched u
WHERE s.gamePk = u.gamePk
''')

conn.unregister("tmp_updates")
conn.close()

print(f"Updated score and sox result fields for {len(df)} existing gamePk(s).")
