import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE OR REPLACE TABLE main.individual_batting_series_running AS
        SELECT
            b.gamePk,
            b.series_id,
            b.playerId,
            b.team_side,
            g.seriesGameNumber,

            -- Raw game stats
            b.atBats,
            b.hits,
            b.homeRuns,
            b.rbi,
            b.totalBases,

            -- Cumulative stats within series
            SUM(b.atBats) OVER (
                PARTITION BY b.series_id, b.playerId
                ORDER BY g.seriesGameNumber
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS series_to_date_at_bats,

            SUM(b.hits) OVER (
                PARTITION BY b.series_id, b.playerId
                ORDER BY g.seriesGameNumber
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS series_to_date_hits,

            SUM(b.homeRuns) OVER (
                PARTITION BY b.series_id, b.playerId
                ORDER BY g.seriesGameNumber
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS series_to_date_home_runs,

            SUM(b.rbi) OVER (
                PARTITION BY b.series_id, b.playerId
                ORDER BY g.seriesGameNumber
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS series_to_date_rbi,

            SUM(b.totalBases) OVER (
                PARTITION BY b.series_id, b.playerId
                ORDER BY g.seriesGameNumber
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS series_to_date_total_bases

        FROM main.individual_batting_stats b
        JOIN main."2025_game_info" g
            ON b.gamePk = g.gamePk;
    """)

print("individual_batting_series_running created.")