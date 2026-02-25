import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    # 1️⃣ Add columns if missing
    con.execute("""
        ALTER TABLE main."2025_game_info"
        ADD COLUMN IF NOT EXISTS home_team_id INTEGER;
    """)

    con.execute("""
        ALTER TABLE main."2025_game_info"
        ADD COLUMN IF NOT EXISTS away_team_id INTEGER;
    """)

    # 2️⃣ Update home_team_id
    con.execute("""
        UPDATE main."2025_game_info" g
        SET home_team_id = t.team_id
        FROM main.teams_reference t
        WHERE g.home_team_name = t.team_name;
    """)

    # 3️⃣ Update away_team_id
    con.execute("""
        UPDATE main."2025_game_info" g
        SET away_team_id = t.team_id
        FROM main.teams_reference t
        WHERE g.away_team_name = t.team_name;
    """)

print("✅ Team IDs successfully populated via team_name.")