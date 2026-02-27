import duckdb

DB_PATH = "../../redsox_25.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE OR REPLACE TABLE main.strikeouts AS

WITH strikeout_pas AS (
    SELECT
        game_pk,
        pa_id,
        team_id,
        batter_id,
        pitcher_id
    FROM main."2025_game_plate_appearance"
    WHERE eventType = 'strikeout'
),

ranked_pitches AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk, p.pa_id
            ORDER BY p.pitch_number DESC
        ) AS rn
    FROM main.pa_plate_events p
    JOIN strikeout_pas s
        ON p.game_pk = s.game_pk
        AND p.pa_id = s.pa_id
)

SELECT
    s.game_pk,
    s.pa_id,
    s.team_id,
    s.batter_id,
    s.pitcher_id,

    p.pitch_type_code,
    p.pitch_type_desc,

    p.code AS final_pitch_code,
    p.description AS final_pitch_description,

    p.pre_balls AS balls_before_pitch,
    p.pre_strikes AS strikes_before_pitch,

    CASE
        WHEN p.code IN ('S','W','T') THEN 'k'
        WHEN p.code = 'C' THEN 'c'
        ELSE NULL
    END AS strikeout_type

FROM strikeout_pas s
JOIN ranked_pitches p
    ON s.game_pk = p.game_pk
    AND s.pa_id = p.pa_id
WHERE p.rn = 1;
""")

con.close()

print("Strikeouts table created successfully.")