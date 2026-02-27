import duckdb

DB_PATH = "../../redsox_25.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE OR REPLACE TABLE main.base_running_attempts AS

SELECT
    game_pk,
    pa_id,
    team_id,
    runner_id,
    origin_base,
    end_base AS target_base,
    movement_reason,

    CASE 
        WHEN movement_reason LIKE 'r_stolen_base_%' THEN 1
        ELSE 0
    END AS successful,

    CASE
        WHEN movement_reason LIKE 'r_caught_stealing_%'
             OR movement_reason LIKE 'r_pickoff_caught_stealing_%'
        THEN 1
        ELSE 0
    END AS caught,

    CASE
        WHEN movement_reason LIKE 'r_pickoff_caught_stealing_%'
        THEN 1
        ELSE 0
    END AS pickoff_component

FROM main."2025_plate_appearance_movement_details"

WHERE movement_reason LIKE 'r_%stealing%'
   OR movement_reason LIKE 'r_stolen_base_%';
""")

con.close()

print("Base running attempts table created.")