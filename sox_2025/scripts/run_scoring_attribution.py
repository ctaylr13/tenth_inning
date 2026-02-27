import duckdb

DB_PATH = "../../redsox_25.duckdb"
con = duckdb.connect(DB_PATH)

print("Building run_scoring_attribution...")

con.execute("""
CREATE OR REPLACE TABLE main.run_scoring_attribution AS

SELECT
    game_pk,
    runner_id,

    origin_pa_id,

    advancement_pa_id AS scoring_pa_id,

    responsible_batter_id,

    inning,
    event,
    event_type

FROM main.runner_base_path

WHERE end_base = 'score'
   OR is_scoring_event = true

ORDER BY game_pk, scoring_pa_id;
""")

con.close()

print("run_scoring_attribution created.")