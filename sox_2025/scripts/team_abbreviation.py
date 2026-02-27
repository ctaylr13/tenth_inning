import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    # ---------------------------------------------------
    # 1️⃣ Add columns if missing
    # ---------------------------------------------------
    con.execute("""
        ALTER TABLE main."2025_game_info"
        ADD COLUMN IF NOT EXISTS home_abbreviation VARCHAR;
    """)

    con.execute("""
        ALTER TABLE main."2025_game_info"
        ADD COLUMN IF NOT EXISTS away_abbreviation VARCHAR;
    """)

    # ---------------------------------------------------
    # 2️⃣ Update home_abbreviation
    # ---------------------------------------------------
    con.execute("""
        UPDATE main."2025_game_info" g
        SET home_abbreviation = t.abbreviation
        FROM main.teams_reference t
        WHERE g.home_team_name = t.team_name;
    """)

    # ---------------------------------------------------
    # 3️⃣ Update away_abbreviation
    # ---------------------------------------------------
    con.execute("""
        UPDATE main."2025_game_info" g
        SET away_abbreviation = t.abbreviation
        FROM main.teams_reference t
        WHERE g.away_team_name = t.team_name;
    """)

print("✅ Abbreviations successfully added.")