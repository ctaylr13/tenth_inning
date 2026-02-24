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
# Create Table (Pitch-Level Grain)
# ---------------------------------------------------
con.execute("""
CREATE TABLE IF NOT EXISTS pa_plate_events (
    game_pk INTEGER,
    team_id INTEGER,
    pa_id INTEGER,
    pitch_number INTEGER,

    batter_id INTEGER,
    pitcher_id INTEGER,

    description VARCHAR,
    code VARCHAR,
    is_in_play BOOLEAN,
    is_strike BOOLEAN,
    is_ball BOOLEAN,
    pitch_type_code VARCHAR,
    pitch_type_desc VARCHAR,
    is_out BOOLEAN,

    balls INTEGER,
    strikes INTEGER,
    outs INTEGER,

    pre_balls INTEGER,
    pre_strikes INTEGER,
    pre_outs INTEGER,

    start_speed DOUBLE,
    end_speed DOUBLE,
    zone INTEGER,
    plate_time DOUBLE,
    extension DOUBLE,

    pX DOUBLE,
    pZ DOUBLE,
    spin_rate INTEGER,

    bat_speed DOUBLE,
    is_sword_swing BOOLEAN,

    PRIMARY KEY (game_pk, pa_id, pitch_number)
)
""")

# ---------------------------------------------------
# Delete Existing Rows For This Game (safe re-run)
# ---------------------------------------------------
con.execute("""
DELETE FROM pa_plate_events
WHERE game_pk = ?
""", (GAME_PK,))

# ---------------------------------------------------
# Insert Pitch Events
# ---------------------------------------------------
for play in all_plays:

    about = play["about"]
    matchup = play["matchup"]

    pa_id = about["atBatIndex"]
    half = about["halfInning"]

    team_id = away_team_id if half == "top" else home_team_id
    batter_id = matchup["batter"]["id"]
    pitcher_id = matchup["pitcher"]["id"]

    play_events = play.get("playEvents", [])

    for event in play_events:

        if not event.get("isPitch"):
            continue

        details = event.get("details", {})
        count = event.get("count", {})
        pre_count = event.get("preCount", {})
        pitch_data = event.get("pitchData", {})
        hit_data = event.get("hitData", {})

        con.execute("""
            INSERT INTO pa_plate_events (
                game_pk,
                team_id,
                pa_id,
                pitch_number,
                batter_id,
                pitcher_id,
                description,
                code,
                is_in_play,
                is_strike,
                is_ball,
                pitch_type_code,
                pitch_type_desc,
                is_out,
                balls,
                strikes,
                outs,
                pre_balls,
                pre_strikes,
                pre_outs,
                start_speed,
                end_speed,
                zone,
                plate_time,
                extension,
                pX,
                pZ,
                spin_rate,
                bat_speed,
                is_sword_swing
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            GAME_PK,
            team_id,
            pa_id,
            event.get("pitchNumber"),

            batter_id,
            pitcher_id,

            details.get("description"),
            details.get("code"),
            details.get("isInPlay"),
            details.get("isStrike"),
            details.get("isBall"),
            details.get("type", {}).get("code"),
            details.get("type", {}).get("description"),
            details.get("isOut"),

            count.get("balls"),
            count.get("strikes"),
            count.get("outs"),

            pre_count.get("balls"),
            pre_count.get("strikes"),
            pre_count.get("outs"),

            pitch_data.get("startSpeed"),
            pitch_data.get("endSpeed"),
            pitch_data.get("zone"),
            pitch_data.get("plateTime"),
            pitch_data.get("extension"),

            pitch_data.get("coordinates", {}).get("pX"),
            pitch_data.get("coordinates", {}).get("pZ"),
            pitch_data.get("breaks", {}).get("spinRate"),

            hit_data.get("batSpeed"),
            hit_data.get("isSwordSwing"),
        ))

con.close()

print(f"Pitch events written for game {GAME_PK}.")