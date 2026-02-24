import requests
import duckdb

DB_PATH = "../../../redsox_25.duckdb"
GAME_PK = 778553

# ---------------------------------------------------
# Pull MLB Data
# ---------------------------------------------------
url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]

home_team_id = data["gameData"]["teams"]["home"]["id"]
away_team_id = data["gameData"]["teams"]["away"]["id"]

# ---------------------------------------------------
# Connect to DuckDB
# ---------------------------------------------------
con = duckdb.connect(DB_PATH)

# ---------------------------------------------------
# Create Table
# ---------------------------------------------------
con.execute("""
CREATE TABLE IF NOT EXISTS game_plate_appearance (
    game_pk INTEGER,
    pa_id INTEGER,
    team_id INTEGER,

    halfInning VARCHAR,
    isTopInning BOOLEAN,
    inning INTEGER,
    isScoringPlay BOOLEAN,
    hasOut BOOLEAN,

    batter_id INTEGER,
    pitcher_id INTEGER,

    type VARCHAR,
    event VARCHAR,
    eventType VARCHAR,
    description VARCHAR,
    rbi INTEGER,
    awayScore INTEGER,
    homeScore INTEGER,
    isOut BOOLEAN,

    balls INTEGER,
    strikes INTEGER,
    outs INTEGER,

    pitch_index INTEGER[],
    action_index INTEGER[],
    runner_index INTEGER[],

    PRIMARY KEY (game_pk, pa_id)
)
""")

# ---------------------------------------------------
# Insert Data
# ---------------------------------------------------
for play in all_plays:

    about = play["about"]
    result = play["result"]
    count = play["count"]
    matchup = play["matchup"]

    pa_id = about["atBatIndex"]

    pitch_index = play.get("pitchIndex", [])
    action_index = play.get("actionIndex", [])
    runner_index = play.get("runnerIndex", [])

    half = about["halfInning"]
    team_id = away_team_id if half == "top" else home_team_id

    con.execute("""
        INSERT OR REPLACE INTO game_plate_appearance
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        GAME_PK,
        pa_id,
        team_id,

        about.get("halfInning"),
        about.get("isTopInning"),
        about.get("inning"),
        about.get("isScoringPlay"),
        about.get("hasOut"),

        matchup.get("batter", {}).get("id"),
        matchup.get("pitcher", {}).get("id"),

        result.get("type"),
        result.get("event"),
        result.get("eventType"),
        result.get("description"),
        result.get("rbi"),
        result.get("awayScore"),
        result.get("homeScore"),
        result.get("isOut"),

        count.get("balls"),
        count.get("strikes"),
        count.get("outs"),

        pitch_index,
        action_index,
        runner_index
    ))

con.close()

print(f"Inserted {len(all_plays)} plate appearances into game_plate_appearance.")