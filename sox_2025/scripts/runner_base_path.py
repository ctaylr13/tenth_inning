import duckdb

DB_PATH = "../../redsox_25.duckdb"
con = duckdb.connect(DB_PATH)

print("Rebuilding runner_base_path with inning-safe propagation...")

con.execute("""
CREATE OR REPLACE TABLE main.runner_base_path AS

WITH joined AS (
    SELECT
        mv.*,
        pa.inning,
        pa.batter_id
    FROM main."2025_plate_appearance_movement_details" mv
    JOIN main."2025_game_plate_appearance" pa
        ON mv.game_pk = pa.game_pk
        AND mv.pa_id = pa.pa_id
),

ordered AS (
    SELECT
        *,
        CASE
            WHEN origin_base IS NULL
                 AND end_base IS NOT NULL
                 AND end_base != 'score'
            THEN pa_id
            ELSE NULL
        END AS origin_marker
    FROM joined
),

propagated AS (
    SELECT
        *,
        MAX(origin_marker) OVER (
            PARTITION BY game_pk, runner_id, inning
            ORDER BY pa_id, play_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS origin_pa_id
    FROM ordered
)

SELECT
    game_pk,
    runner_id,
    origin_pa_id,
    pa_id AS advancement_pa_id,
    batter_id AS responsible_batter_id,
    inning,
    origin_base,
    start_base,
    end_base,
    play_index,
    is_out,
    is_scoring_event,
    event,
    event_type,
    movement_reason

FROM propagated
ORDER BY game_pk, runner_id, inning, pa_id, play_index;
""")

con.close()

print("runner_base_path rebuilt correctly.")