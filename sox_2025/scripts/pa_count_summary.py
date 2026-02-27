import duckdb

DB_PATH = "../../redsox_25.duckdb"

con = duckdb.connect(DB_PATH)

con.execute("""
CREATE OR REPLACE TABLE main.pa_count_summary AS

WITH ordered_pitches AS (
    SELECT
        game_pk,
        pa_id,
        team_id,
        batter_id,
        pitcher_id,
        pitch_number,
        pre_balls,
        pre_strikes,
        balls,
        strikes,
        is_strike,
        is_in_play,
        code,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk, pa_id
            ORDER BY pitch_number
        ) AS pitch_seq
    FROM main.pa_plate_events
),

pa_agg AS (
    SELECT
        game_pk,
        pa_id,
        ANY_VALUE(team_id) AS team_id,
        ANY_VALUE(batter_id) AS batter_id,
        ANY_VALUE(pitcher_id) AS pitcher_id,

        COUNT(*) AS pitch_count,

        MAX(balls) AS final_balls,
        MAX(strikes) AS final_strikes,

        MAX(pre_strikes) AS max_strikes_seen,
        MAX(pre_balls) AS max_balls_seen,

        MAX(CASE WHEN pre_strikes >= 2 THEN 1 ELSE 0 END) AS went_to_two_strikes,
        MAX(CASE WHEN pre_balls >= 3 THEN 1 ELSE 0 END) AS went_to_three_balls,

        MAX(CASE WHEN pre_balls = 0 AND pre_strikes = 2 THEN 1 ELSE 0 END) AS reached_0_2,
        MAX(CASE WHEN pre_balls = 3 AND pre_strikes = 0 THEN 1 ELSE 0 END) AS reached_3_0,
        MAX(CASE WHEN pre_balls = 3 AND pre_strikes = 2 THEN 1 ELSE 0 END) AS reached_3_2,

        MAX(CASE 
            WHEN pitch_seq = 1 AND is_strike = TRUE THEN 1 
            ELSE 0 
        END) AS first_pitch_strike,

        -- Foul tips
        SUM(CASE WHEN code = 'T' THEN 1 ELSE 0 END) AS foul_tips_total,

        SUM(CASE 
            WHEN code = 'T' AND pre_strikes < 2 THEN 1 
            ELSE 0 
        END) AS foul_tips_pre_0_2,

        SUM(CASE 
            WHEN code = 'T' AND pre_strikes >= 2 THEN 1 
            ELSE 0 
        END) AS foul_tips_after_0_2,

        -- Bonus pitches (after 2 strikes)
        SUM(CASE 
            WHEN pre_strikes >= 2 THEN 1 
            ELSE 0 
        END) AS bonus_pitches,

        -- Two-strike diagnostics
        SUM(CASE 
            WHEN pre_strikes = 2 THEN 1 
            ELSE 0 
        END) AS total_two_strike_pitches,

        SUM(CASE 
            WHEN pre_strikes = 2 AND code = 'F' THEN 1 
            ELSE 0 
        END) AS two_strike_foul_balls_total,

        SUM(CASE 
            WHEN pre_strikes = 2 
                 AND code IN ('S','W','T') THEN 1 
            ELSE 0 
        END) AS two_strike_whiffs,

        SUM(CASE 
            WHEN pre_strikes = 2 
                 AND is_in_play = TRUE THEN 1 
            ELSE 0 
        END) AS two_strike_bip,

        -- Survival events (foul or BIP with 2 strikes)
        SUM(CASE 
            WHEN pre_strikes = 2 
                 AND (code = 'F' OR is_in_play = TRUE) THEN 1 
            ELSE 0 
        END) AS two_strike_survival_events

    FROM ordered_pitches
    GROUP BY game_pk, pa_id
)

SELECT *
FROM pa_agg;
""")

con.close()

print("Enhanced PA count summary with full two-strike diagnostics created.")