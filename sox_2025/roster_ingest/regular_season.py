import requests
import pandas as pd
import duckdb
from datetime import datetime

# Config
DB_PATH = "redsox_25.duckdb"
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

# Build schedule rows. For each date block, use totalGames to set doubleheader flag.
records = []
for date_block in data.get("dates", []):
    total_games = date_block.get("totalGames", 0)
    doubleheader_flag = True if total_games > 1 else False
    for game in date_block.get("games", []):
        pk = game.get("gamePk")
        gd = game.get("gameDate")
        official = game.get("officialDate") or (gd[:10] if gd else None)
        if pk and gd:
            records.append({
                "gamePk": int(pk),
                "gameDate": gd,
                "officialDate": official,
                "doubleheader": doubleheader_flag
            })

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
