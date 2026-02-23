import requests
import duckdb

DB_PATH = "../../redsox_25.duckdb"
GAME_PK = 776983

# ---------------------------
# Fetch MLB game data
# ---------------------------
url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

plays = data["liveData"]["plays"]["allPlays"]

# ---------------------------
# Connect to DuckDB
# ---------------------------
con = duckdb.connect(DB_PATH)

# ---------------------------
# Create pitches table
# ---------------------------
con.execute("""
CREATE TABLE IF NOT EXISTS pitches (
    game_pk      INTEGER NOT NULL,
    pa_id        INTEGER NOT NULL,
    pitch_number INTEGER NOT NULL,
    pitch_call   VARCHAR NOT NULL,

    PRIMARY KEY (game_pk, pa_id, pitch_number)
);
""")

# ---------------------------
# Collect pitch rows
# ---------------------------
pitch_rows = []

for play in plays:
    pa_id = play["about"]["atBatIndex"]

    for ev in play.get("playEvents", []):
        if not ev.get("isPitch"):
            continue

        pitch_number = ev.get("pitchNumber")
        if pitch_number is None:
            continue

        pitch_call = ev["details"]["call"]["code"]

        pitch_rows.append((
            GAME_PK,
            pa_id,
            pitch_number,
            pitch_call
        ))

print(f"Extracted {len(pitch_rows)} pitches")

# ---------------------------
# Insert (ignore duplicates)
# ---------------------------
con.executemany("""
INSERT OR IGNORE INTO pitches
VALUES (?, ?, ?, ?)
""", pitch_rows)

print("Inserted into DuckDB")

con.close()