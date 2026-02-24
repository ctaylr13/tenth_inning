import requests
import duckdb

DB_PATH = "../../../redsox_25.duckdb"
GAME_PK = 778553

# ---------------------------------------------------
# Pull API Data
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
# Create Table (movement only)
# ---------------------------------------------------
con.execute("""
CREATE TABLE IF NOT EXISTS main."2025_plate_appearance_movement_details" (
    game_pk INTEGER,
    pa_id INTEGER,
    team_id INTEGER,

    runner_id INTEGER,

    origin_base VARCHAR,
    start_base VARCHAR,
    end_base VARCHAR,
    out_base VARCHAR,
    is_out BOOLEAN,

    event VARCHAR,
    event_type VARCHAR,
    movement_reason VARCHAR,
    responsible_pitcher INTEGER,
    is_scoring_event BOOLEAN,
    rbi BOOLEAN,
    earned BOOLEAN,
    team_unearned BOOLEAN,
    play_index INTEGER
)
""")

# ---------------------------------------------------
# Insert Data
# ---------------------------------------------------
for play in all_plays:

    about = play["about"]
    pa_id = about["atBatIndex"]
    half = about["halfInning"]

    team_id = away_team_id if half == "top" else home_team_id

    runners = play.get("runners", [])

    for runner in runners:

        movement = runner.get("movement", {})
        details = runner.get("details", {})

        runner_id = details.get("runner", {}).get("id")
        responsible_pitcher_obj = details.get("responsiblePitcher")
        responsible_pitcher = responsible_pitcher_obj.get("id") if responsible_pitcher_obj else None

        con.execute("""
            INSERT INTO main."2025_plate_appearance_movement_details"
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            GAME_PK,
            pa_id,
            team_id,
            runner_id,
            movement.get("originBase"),
            movement.get("start"),
            movement.get("end"),
            movement.get("outBase"),
            movement.get("isOut"),
            details.get("event"),
            details.get("eventType"),
            details.get("movementReason"),
            responsible_pitcher,
            details.get("isScoringEvent"),
            details.get("rbi"),
            details.get("earned"),
            details.get("teamUnearned"),
            details.get("playIndex")
        ))

con.close()

print(f"Movement details written for game {GAME_PK}.")