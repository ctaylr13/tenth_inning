import duckdb

DB_PATH = "../../redsox_25.duckdb"

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE OR REPLACE TABLE main.game_roster_lineup_trends AS

        WITH team_games AS (
            SELECT
                g.gamePk,
                g.officialDate,
                g.home_team_id,
                g.away_team_id,
                ROW_NUMBER() OVER (
                    PARTITION BY g.home_team_id
                    ORDER BY g.officialDate, g.gamePk
                ) AS home_game_number,

                ROW_NUMBER() OVER (
                    PARTITION BY g.away_team_id
                    ORDER BY g.officialDate, g.gamePk
                ) AS away_game_number
            FROM main."2025_game_info" g
        ),

        roster_with_team_seq AS (
            SELECT
                r.*,
                g.officialDate,
                CASE 
                    WHEN r.parentTeamId = g.home_team_id
                        THEN tg.home_game_number
                    ELSE tg.away_game_number
                END AS team_game_number
            FROM main.game_rosters r
            JOIN main."2025_game_info" g
                ON r.gamePk = g.gamePk
            JOIN team_games tg
                ON r.gamePk = tg.gamePk
            WHERE r.is_starter = TRUE
        )

        SELECT
            curr.gamePk,
            curr.playerId,
            curr.fullName,
            curr.parentTeamId,
            curr.battingOrder,
            curr.team_game_number,

            prev.battingOrder AS previous_batting_order,

            CASE
                WHEN prev.battingOrder IS NULL THEN NULL
                WHEN curr.battingOrder < prev.battingOrder THEN 'UP'
                WHEN curr.battingOrder > prev.battingOrder THEN 'DOWN'
                ELSE 'SAME'
            END AS lineup_movement

        FROM roster_with_team_seq curr

        LEFT JOIN roster_with_team_seq prev
            ON curr.playerId = prev.playerId
            AND curr.parentTeamId = prev.parentTeamId
            AND curr.team_game_number = prev.team_game_number + 1;
    """)

print("game_roster_lineup_trends created.")