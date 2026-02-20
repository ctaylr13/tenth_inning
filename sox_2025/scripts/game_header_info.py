import duckdb

DB_PATH = "../../redsox_25.duckdb"  # adjust path if needed
OUT_TABLE = '"2025_game_info"'

SQL = f"""
CREATE OR REPLACE TABLE {OUT_TABLE} AS
SELECT
  s."officialDate",
  (SELECT t."team_name" FROM "teams_reference" t WHERE t."team_id" = s."away_team_id") AS away_team_name,
  (SELECT t."team_name" FROM "teams_reference" t WHERE t."team_id" = s."home_team_id") AS home_team_name,
  (SELECT t."venue_name" FROM "teams_reference" t WHERE t."venue_id" = s."home_venue_id") AS home_venue_name,
  s."gamesInSeries",
  s."seriesGameNumber",
  s."home_score",
  s."away_score",
  s."sox_is_winner",
  s."sox_wins",
  s."sox_losses",
  s."sox_pct",
  s."attendance",
  s."gameDurationMinutes",
  s."home_team_jersey_text",
  s."away_team_jersey_text",
  (SELECT r."uniformAssetText" FROM "redsox_uniforms" r WHERE r."uniformAssetId" = s."jersey_asset_id") AS jersey_asset_text,
  s."stadium_fill_percent",
  s."home_manager",
  s."away_manager",
  s."home_gamesPlayed",
  s."away_gamesPlayed",
  s."home_divisionLeader",
  s."home_wins",
  s."home_losses",
  s."away_divisionLeader",
  s."away_wins",
  s."away_losses",
  s."sox_games_played",
  s."game_start_12hr",
  s."game_end_12hr",
  (SELECT v."turf_type"         FROM "venue_game_stats" v WHERE v."gamePk" = s."gamePk") AS turf_type,
  (SELECT v."roof_type"         FROM "venue_game_stats" v WHERE v."gamePk" = s."gamePk") AS roof_type,
  (SELECT v."weather_condition" FROM "venue_game_stats" v WHERE v."gamePk" = s."gamePk") AS weather_condition,
  (SELECT v."weather_temp"      FROM "venue_game_stats" v WHERE v."gamePk" = s."gamePk") AS weather_temp,
  (SELECT v."weather_wind"      FROM "venue_game_stats" v WHERE v."gamePk" = s."gamePk") AS weather_wind,
  (SELECT g."home_plate_name"  FROM "game_officials" g WHERE g."gamePk" = s."gamePk") AS home_plate_ump,
  (SELECT g."first_base_name"  FROM "game_officials" g WHERE g."gamePk" = s."gamePk") AS first_base_ump,
  (SELECT g."second_base_name" FROM "game_officials" g WHERE g."gamePk" = s."gamePk") AS second_base_ump,
  (SELECT g."third_base_name"  FROM "game_officials" g WHERE g."gamePk" = s."gamePk") AS third_base_ump
FROM "2025_schedule" s
ORDER BY s."officialDate", s."gamePk";
"""

conn = duckdb.connect(DB_PATH)
try:
    conn.execute(SQL)
    print("Created/updated table 2025_game_info")
finally:
    conn.close()