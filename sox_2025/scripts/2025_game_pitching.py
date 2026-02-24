import duckdb

DB_PATH = "../../redsox_25.duckdb"
OUT_TABLE = 'main."2025_game_pitching"'

SQL = f"""
CREATE OR REPLACE TABLE {OUT_TABLE} AS
SELECT
  ips.gamePk,
  ips.playerId,
  pr.fullName,
  pr.firstName,
  pr.lastName,
  pr.primaryNumber,
  pr.pitchHand_code,
  ips.pitcher_order,
  ips.team_side,
  ips.numberOfPitches,
  ips.battersFaced,
  ips.atBats,
  ips.hits,
  ips.runs,
  ips.earnedRuns,
  ips.strikeOuts,
  ips.baseOnBalls,
  ips.intentionalWalks,
  ips.wins,
  ips.losses,
  ips.balls,
  ips.strikes,
  ips.innings_pitched_display
FROM redsox_25.individual_pitching_stats ips
LEFT JOIN redsox_25.player_reference pr
  ON ips.playerId = pr.playerId
"""

conn = duckdb.connect(DB_PATH)
try:
    conn.execute(SQL)
    print("Created/updated table 2025_game_pitching")
finally:
    conn.close()