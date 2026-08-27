\set ON_ERROR_STOP on

-- Source: redsox_25.duckdb at SHA-256 1c0681d8ee64b3d5b1ccf1efe3ac0e3b0b213243444b3d422067932ddf74e16c
BEGIN;

INSERT INTO team (team_id, name, abbreviation)
VALUES
    (111, 'Boston Red Sox', 'BOS'),
    (116, 'Detroit Tigers', 'DET');

INSERT INTO team_season (team_id, season, ingest_status)
VALUES (111, 2025, NULL);

INSERT INTO game (
    game_pk,
    official_date,
    game_time_utc,
    coded_game_state,
    detailed_state,
    is_doubleheader,
    game_number,
    rescheduled_from,
    away_team_id,
    home_team_id,
    away_score,
    home_score
)
VALUES (
    777940,
    DATE '2025-05-13',
    NULL,
    NULL,
    NULL,
    FALSE,
    1,
    NULL,
    111,
    116,
    9,
    10
);

INSERT INTO team_season_game (
    team_id,
    season,
    game_pk,
    did_win,
    cumulative_wins,
    cumulative_losses,
    standings_position
)
VALUES (111, 2025, 777940, FALSE, 22, 22, NULL);

COMMIT;
