import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE OR REPLACE TABLE main.individual_batting_series_stats AS
        SELECT
            series_id,
            playerId,
            team_side,

            COUNT(DISTINCT gamePk) AS games_played,

            SUM(atBats) AS at_bats,
            SUM(hits) AS hits,
            SUM(doubles) AS doubles,
            SUM(triples) AS triples,
            SUM(homeRuns) AS home_runs,
            SUM(rbi) AS rbi,
            SUM(runs) AS runs,
            SUM(baseOnBalls) AS walks,
            SUM(intentionalWalks) AS intentional_walks,
            SUM(hitByPitch) AS hit_by_pitch,
            SUM(strikeOuts) AS strikeouts,
            SUM(stolenBases) AS stolen_bases,
            SUM(caughtStealing) AS caught_stealing,
            SUM(totalBases) AS total_bases,
            SUM(plateAppearances) AS plate_appearances,
            SUM(sacFlies) AS sac_flies,
            SUM(sacBunts) AS sac_bunts,

            -- Recalculate rate stats properly

            CASE 
                WHEN SUM(atBats) > 0 
                THEN SUM(hits) * 1.0 / SUM(atBats)
                ELSE NULL
            END AS avg,

            CASE 
                WHEN (SUM(atBats) + SUM(baseOnBalls) + SUM(hitByPitch) + SUM(sacFlies)) > 0
                THEN (SUM(hits) + SUM(baseOnBalls) + SUM(hitByPitch)) * 1.0 /
                     (SUM(atBats) + SUM(baseOnBalls) + SUM(hitByPitch) + SUM(sacFlies))
                ELSE NULL
            END AS obp,

            CASE
                WHEN SUM(atBats) > 0
                THEN SUM(totalBases) * 1.0 / SUM(atBats)
                ELSE NULL
            END AS slg

        FROM main.individual_batting_stats
        GROUP BY series_id, playerId, team_side;
    """)

print("individual_batting_series_stats created.")