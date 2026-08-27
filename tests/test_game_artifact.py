from pathlib import Path

import duckdb
import pytest

from artifacts import game_artifact_pb2
from artifacts.game_artifact import (
    deserialize_game,
    load_game_artifact,
    serialize_game,
    write_game_artifact,
)


@pytest.fixture
def legacy_game_db(tmp_path: Path) -> Path:
    path = tmp_path / "legacy-game.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("""
            CREATE TABLE "2025_schedule" (
                gamePk BIGINT, officialDate DATE, gameDate TIMESTAMP,
                away_score INTEGER, home_score INTEGER, doubleheader BOOLEAN,
                gameNumber INTEGER
            );
            INSERT INTO "2025_schedule"
            VALUES (777940, DATE '2025-05-13', TIMESTAMP '2025-05-13 22:40:00',
                    9, 10, FALSE, 1);

            CREATE TABLE "2025_game_info" (
                gamePk BIGINT, away_team_id BIGINT, home_team_id BIGINT,
                away_team_name VARCHAR, home_team_name VARCHAR
            );
            INSERT INTO "2025_game_info"
            VALUES (777940, 111, 116, 'Boston Red Sox', 'Detroit Tigers');

            CREATE TABLE "2025_game_plate_appearance" (
                game_pk INTEGER, pa_id INTEGER, team_id INTEGER,
                halfInning VARCHAR, inning INTEGER, batter_id INTEGER,
                pitcher_id INTEGER, event VARCHAR, eventType VARCHAR,
                description VARCHAR, rbi INTEGER, awayScore INTEGER,
                homeScore INTEGER, isOut BOOLEAN, balls INTEGER,
                strikes INTEGER, outs INTEGER
            );
            INSERT INTO "2025_game_plate_appearance"
            VALUES (777940, 0, 111, 'top', 1, 680776, 663947,
                    'Flyout', 'field_out', 'Duran flies out.', 0, 0, 0,
                    TRUE, 3, 2, 1);

            CREATE TABLE pa_plate_events (
                game_pk INTEGER, pa_id INTEGER, pitch_number INTEGER,
                description VARCHAR, code VARCHAR, is_in_play BOOLEAN,
                is_strike BOOLEAN, is_ball BOOLEAN, is_out BOOLEAN,
                pitch_type_code VARCHAR, pitch_type_desc VARCHAR,
                balls INTEGER, strikes INTEGER, outs INTEGER,
                pre_balls INTEGER, pre_strikes INTEGER, pre_outs INTEGER,
                start_speed DOUBLE, end_speed DOUBLE, zone INTEGER,
                plate_time DOUBLE, extension DOUBLE, pX DOUBLE, pZ DOUBLE,
                spin_rate INTEGER, bat_speed DOUBLE, is_sword_swing BOOLEAN,
                launch_speed DOUBLE, launch_angle DOUBLE, total_distance DOUBLE,
                trajectory VARCHAR, hardness VARCHAR, hit_location VARCHAR,
                hit_coord_x DOUBLE, hit_coord_y DOUBLE, hit_probability DOUBLE
            );
            INSERT INTO pa_plate_events (
                game_pk, pa_id, pitch_number, description, code,
                is_in_play, is_strike, is_ball, is_out,
                pitch_type_code, pitch_type_desc, balls, strikes, outs,
                pre_balls, pre_strikes, pre_outs, start_speed, end_speed,
                zone, pX, pZ, spin_rate
            ) VALUES (
                777940, 0, 1, 'Ball', 'B', FALSE, FALSE, TRUE, FALSE,
                'ST', 'Sweeper', 1, 0, 0, 0, 0, 0, 81.3, 74.6,
                13, -1.25, 1.55, 2700
            );
        """)
    return path


def test_builds_and_decodes_game_with_generated_code(legacy_game_db: Path):
    with duckdb.connect(str(legacy_game_db), read_only=True) as conn:
        payload = serialize_game(conn, 777940)

    artifact = deserialize_game(payload)

    assert isinstance(artifact, game_artifact_pb2.GameArtifact)
    assert artifact.schema_version == 1
    assert artifact.metadata.game_pk == 777940
    assert artifact.metadata.game_time_utc == "2025-05-13T22:40:00Z"
    assert (artifact.metadata.away_team_name, artifact.metadata.home_team_name) == (
        "Boston Red Sox",
        "Detroit Tigers",
    )
    assert len(artifact.plate_appearances) == 1
    appearance = artifact.plate_appearances[0]
    assert appearance.half_inning == game_artifact_pb2.HALF_INNING_TOP
    assert appearance.event_type == "field_out"
    assert len(appearance.pitches) == 1
    pitch = appearance.pitches[0]
    assert (pitch.pitch_number, pitch.pitch_type_code, pitch.spin_rate) == (
        1,
        "ST",
        2700,
    )
    assert pitch.HasField("is_ball") and pitch.is_ball is True
    assert not pitch.HasField("bat_speed")


def test_serialization_is_deterministic_and_can_be_written(
    legacy_game_db: Path, tmp_path: Path
):
    output = tmp_path / "game-777940.pb"
    with duckdb.connect(str(legacy_game_db), read_only=True) as conn:
        expected = serialize_game(conn, 777940)

    byte_count = write_game_artifact(legacy_game_db, 777940, output)

    assert output.read_bytes() == expected
    assert byte_count == len(expected)


def test_missing_legacy_game_is_explicit(legacy_game_db: Path):
    with (
        duckdb.connect(str(legacy_game_db), read_only=True) as conn,
        pytest.raises(LookupError, match="999999"),
    ):
        load_game_artifact(conn, 999999)
