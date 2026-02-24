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

# ---------------------------------------------------
# Connect to DuckDB
# ---------------------------------------------------
con = duckdb.connect(DB_PATH)

# ---------------------------------------------------
# Ensure Columns Exist
# ---------------------------------------------------
con.execute("""
ALTER TABLE "2025_game_plate_appearance"
ADD COLUMN IF NOT EXISTS b_pa INTEGER
""")

con.execute("""
ALTER TABLE "2025_game_plate_appearance"
ADD COLUMN IF NOT EXISTS p_pa INTEGER
""")

con.execute("""
ALTER TABLE "2025_game_plate_appearance"
ADD COLUMN IF NOT EXISTS b_ab INTEGER
""")

con.execute("""
ALTER TABLE "2025_game_plate_appearance"
ADD COLUMN IF NOT EXISTS p_ab INTEGER
""")

# ---------------------------------------------------
# Update Rows for This Game
# ---------------------------------------------------
for play in all_plays:

    pa_id = play["about"]["atBatIndex"]
    credits = play.get("credits", [])

    # Default values
    b_pa = None
    p_pa = None
    b_ab = None
    p_ab = None

    # Extract credit values
    for credit in credits:
        credit_type = credit.get("credit")
        player_id = credit.get("player", {}).get("id")

        if credit_type == "b_pa":
            b_pa = player_id
        elif credit_type == "p_pa":
            p_pa = player_id
        elif credit_type == "b_ab":
            b_ab = player_id
        elif credit_type == "p_ab":
            p_ab = player_id

    # Update table
    con.execute("""
        UPDATE main."2025_game_plate_appearance"
        SET b_pa = ?,
            p_pa = ?,
            b_ab = ?,
            p_ab = ?
        WHERE game_pk = ?
          AND pa_id = ?
    """, (
        b_pa,
        p_pa,
        b_ab,
        p_ab,
        GAME_PK,
        pa_id
    ))

con.close()

print(f"Credits updated for game {GAME_PK}.")