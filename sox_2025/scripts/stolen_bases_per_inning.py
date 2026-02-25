import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE OR REPLACE TABLE main.inning_stolen_bases AS

        SELECT
            pa.game_pk,
            pa.inning,
            pa.team_id,
            COUNT(*) AS stolen_bases_in_inning

        FROM main."2025_plate_appearance_movement_details" mv

        JOIN main."2025_game_plate_appearance" pa
            ON mv.game_pk = pa.game_pk
            AND mv.pa_id = pa.pa_id

        WHERE mv.movement_reason IN (
            'r_stolen_base_2b',
            'r_stolen_base_3b',
            'r_stolen_base_home'
        )

        GROUP BY pa.game_pk, pa.inning, pa.team_id
        ORDER BY pa.game_pk, pa.inning, pa.team_id;
    """)

print("inning_stolen_bases created.")