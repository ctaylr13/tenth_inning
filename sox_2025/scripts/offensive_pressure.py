import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE OR REPLACE TABLE main.inning_offensive_pressure AS

        WITH pa_counts AS (
            SELECT
                game_pk,
                inning,
                team_id,

                COUNT(*) AS pa_in_inning,

                SUM(
                    CASE 
                        WHEN eventType NOT IN (
                            'walk',
                            'intent_walk',
                            'hit_by_pitch',
                            'sac_fly',
                            'sac_bunt',
                            'catcher_interf'
                        )
                        THEN 1 ELSE 0
                    END
                ) AS at_bats_in_inning

            FROM main."2025_game_plate_appearance"
            GROUP BY game_pk, inning, team_id
        ),

        pa_with_diff AS (
            SELECT
                game_pk,
                inning,
                team_id,
                pa_in_inning,
                at_bats_in_inning,
                (pa_in_inning - 3) AS pa_above_3,

                -- Team PA minus opponent PA in same inning
                pa_in_inning -
                (SUM(pa_in_inning) OVER (
                    PARTITION BY game_pk, inning
                ) - pa_in_inning)
                AS pa_diff

            FROM pa_counts
        )

        SELECT
            game_pk,
            inning,
            team_id,
            pa_in_inning,
            at_bats_in_inning,
            pa_above_3,
            pa_diff,

            SUM(pa_diff) OVER (
                PARTITION BY game_pk, team_id
                ORDER BY inning
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_pa_diff

        FROM pa_with_diff
        ORDER BY game_pk, inning, team_id;
    """)

print("inning_offensive_pressure table created.")
