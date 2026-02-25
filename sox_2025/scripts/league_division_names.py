import duckdb

DB_PATH = "../../redsox_25.duckdb"

LEAGUE_CSV = "mlb_leagues.csv"
DIVISION_CSV = "mlb_divisions.csv"

with duckdb.connect(DB_PATH) as con:

    # -------------------------------------------------
    # 1️⃣ Add columns if they don't exist
    # -------------------------------------------------
    con.execute("""
        ALTER TABLE main.teams_reference
        ADD COLUMN IF NOT EXISTS league_name VARCHAR;
    """)

    con.execute("""
        ALTER TABLE main.teams_reference
        ADD COLUMN IF NOT EXISTS division_name VARCHAR;
    """)

    # -------------------------------------------------
    # 2️⃣ Load CSVs into temp views
    # -------------------------------------------------
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW league_lookup AS
        SELECT * FROM read_csv_auto('{LEAGUE_CSV}');
    """)

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW division_lookup AS
        SELECT * FROM read_csv_auto('{DIVISION_CSV}');
    """)

    # -------------------------------------------------
    # 3️⃣ Update league_name
    # -------------------------------------------------
    con.execute("""
        UPDATE main.teams_reference t
        SET league_name = l.league_name
        FROM league_lookup l
        WHERE t.league_id = l.league_id;
    """)

    # -------------------------------------------------
    # 4️⃣ Update division_name
    # -------------------------------------------------
    con.execute("""
        UPDATE main.teams_reference t
        SET division_name = d.division_name
        FROM division_lookup d
        WHERE t.division_id = d.division_id;
    """)

print("teams_reference successfully enriched with league and division names.")