import requests
import duckdb

DB_PATH = "../../../redsox_25.duckdb"
GAME_PK = 778553

# ---------------------------------------------------
# Pull MLB Data
# ---------------------------------------------------
url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

plays = data["liveData"]["plays"]["allPlays"]

home_team_id = data["gameData"]["teams"]["home"]["id"]
away_team_id = data["gameData"]["teams"]["away"]["id"]

# ---------------------------------------------------
# Connect to DuckDB
# ---------------------------------------------------
con = duckdb.connect(DB_PATH)

con.execute("""
CREATE TABLE IF NOT EXISTS plate_appearance_info (
    game_pk INTEGER,
    pa_id INTEGER,
    inning INTEGER,
    half VARCHAR,
    team_id INTEGER,
    batter_id INTEGER,
    pitcher_id INTEGER,
    event_type VARCHAR,
    event_desc VARCHAR,
    PRIMARY KEY (game_pk, pa_id)
)
""")

# ---------------------------------------------------
# Insert Plate Appearances
# ---------------------------------------------------
for play in plays:
    about = play["about"]
    matchup = play["matchup"]
    result = play["result"]

    half = about["halfInning"]

    team_id = away_team_id if half == "top" else home_team_id

    con.execute("""
        INSERT OR REPLACE INTO plate_appearance_info
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        GAME_PK,
        about["atBatIndex"],
        about["inning"],
        half,
        team_id,
        matchup["batter"]["id"],
        matchup["pitcher"]["id"],
        result["eventType"],
        result.get("description")
    ))

con.close()

print("Inserted", len(plays), "plate appearances into plate_appearance_info.")