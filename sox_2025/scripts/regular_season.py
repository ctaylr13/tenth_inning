import requests
import pandas as pd
import duckdb
from datetime import datetime

# Config
DB_PATH = "../../redsox_25.duckdb"
TEAM_ID = 111
BASE_URL = "https://statsapi.mlb.com/api/v1/schedule"
HYDRATE = "team,lineups"
SPORT_ID = 1

START_DATE = "2025-03-27"
END_DATE = "2025-09-28"

# 1) Generate calendar rows
dates = pd.date_range(start=START_DATE, end=END_DATE, freq="D")
df_calendar = pd.DataFrame({
    "the_date": dates.date,
    "iso_date": dates.strftime("%Y-%m-%d"),
    "day_of_week": dates.day_name(),
    "year": dates.year,
    "month": dates.month,
    "day": dates.day
})

# 2) Fetch schedule data from MLB API for the date range
params = {
    "hydrate": HYDRATE,
    "sportId": SPORT_ID,
    "startDate": START_DATE,
    "endDate": END_DATE,
    "teamId": TEAM_ID,
}
resp = requests.get(BASE_URL, params=params, timeout=60)
resp.raise_for_status()
data = resp.json()

# A postponed game is listed under BOTH its original date block and its makeup
# date block, under one gamePk -- 167 entries for 162 games in 2025. Appending
# every entry puts duplicate gamePks in the table, which then makes every later
# `UPDATE ... WHERE s.gamePk = u.gamePk` enrichment write to an arbitrary row.
def rank(game):
    """Higher wins when one gamePk shows up in two date blocks."""
    status = (game.get("status") or {}).get("detailedState")
    game_date = (game.get("gameDate") or "")[:10]
    return (status != "Postponed", game_date == game.get("officialDate"))


best = {}
for date_block in data.get("dates", []):
    for game in date_block.get("games", []):
        pk, gd = game.get("gamePk"), game.get("gameDate")
        if not (pk and gd):
            continue
        pk = int(pk)
        if pk not in best or rank(game) > rank(best[pk]):
            best[pk] = game

records = [
    {
        "gamePk": int(g["gamePk"]),
        "gameDate": g["gameDate"],
        "officialDate": g.get("officialDate") or g["gameDate"][:10],
        # Per-game, not per-date: totalGames > 1 also flagged the unrelated game
        # that merely shared a makeup date.
        "doubleheader": g.get("doubleHeader") in ("Y", "S"),
    }
    for g in best.values()
]

df_schedule = pd.DataFrame(records)
if not df_schedule.empty:
    df_schedule["gameDate"] = pd.to_datetime(df_schedule["gameDate"], utc=True)
    df_schedule["officialDate"] = pd.to_datetime(df_schedule["officialDate"]).dt.date

# 3) Write to DuckDB (fresh start: drop/recreate tables)
conn = duckdb.connect(DB_PATH)

# Drop tables if they exist to start fresh
conn.execute('DROP TABLE IF EXISTS "calendar"')
conn.execute('DROP TABLE IF EXISTS "2025_schedule"')

# Create calendar table
conn.execute('''
CREATE TABLE "calendar" (
  the_date DATE,
  iso_date VARCHAR,
  day_of_week VARCHAR,
  year INTEGER,
  month INTEGER,
  day INTEGER
)
''')

# Create schedule table with doubleheader boolean
conn.execute('''
CREATE TABLE "2025_schedule" (
  gamePk BIGINT,
  gameDate TIMESTAMP,
  officialDate DATE,
  doubleheader BOOLEAN
)
''')

# Insert calendar
if not df_calendar.empty:
    conn.register("tmp_cal", df_calendar)
    conn.execute('INSERT INTO "calendar" SELECT the_date::date, iso_date, day_of_week, year, month, day FROM tmp_cal')
    conn.unregister("tmp_cal")

# Insert schedule
if not df_schedule.empty:
    conn.register("tmp_sched", df_schedule)
    conn.execute('INSERT INTO "2025_schedule" SELECT gamePk, gameDate::timestamp, officialDate::date, doubleheader FROM tmp_sched')
    conn.unregister("tmp_sched")

conn.close()

print(f"Done. Calendar rows: {len(df_calendar)}. Schedule rows: {len(df_schedule)}.")
