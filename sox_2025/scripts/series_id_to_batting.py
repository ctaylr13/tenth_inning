import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        ALTER TABLE main.individual_batting_stats
        ADD COLUMN IF NOT EXISTS series_id BIGINT;
    """)

    con.execute("""
        UPDATE main.individual_batting_stats b
        SET series_id = g.series_id
        FROM main."2025_game_info" g
        WHERE b.gamePk = g.gamePk;
    """)

print("series_id added to individual_batting_stats.")