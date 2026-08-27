"""Build a versioned game artifact from the legacy DuckDB schema."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from artifacts import game_artifact_pb2

SCHEMA_VERSION = 1


def _rows_as_dicts(cursor: duckdb.DuckDBPyConnection) -> Iterable[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return (dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def _iso_utc(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _iso_date(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _set_present(message: Any, **values: Any) -> None:
    """Set optional protobuf scalars only when DuckDB did not return NULL."""
    for field, value in values.items():
        if value is not None:
            setattr(message, field, value)


def _half_inning(value: str | None) -> int:
    halves = {
        "top": game_artifact_pb2.HALF_INNING_TOP,
        "bottom": game_artifact_pb2.HALF_INNING_BOTTOM,
    }
    return halves.get(value or "", game_artifact_pb2.HALF_INNING_UNSPECIFIED)


def load_game_artifact(
    conn: duckdb.DuckDBPyConnection, game_pk: int
) -> game_artifact_pb2.GameArtifact:
    """Read one legacy game and return its generated protobuf message."""
    game_cursor = conn.execute(
        """
        SELECT
            schedule.gamePk AS game_pk,
            schedule.officialDate AS official_date,
            schedule.gameDate AS game_time_utc,
            info.away_team_id,
            info.home_team_id,
            info.away_team_name,
            info.home_team_name,
            schedule.away_score,
            schedule.home_score,
            schedule.doubleheader AS is_doubleheader,
            schedule.gameNumber AS game_number
        FROM "2025_schedule" AS schedule
        JOIN "2025_game_info" AS info ON info.gamePk = schedule.gamePk
        WHERE schedule.gamePk = ?
        """,
        [game_pk],
    )
    rows = list(_rows_as_dicts(game_cursor))
    if not rows:
        raise LookupError(f"No legacy game with gamePk {game_pk}.")
    if len(rows) != 1:
        raise ValueError(
            f"Expected one legacy row for gamePk {game_pk}, got {len(rows)}."
        )

    row = rows[0]
    artifact = game_artifact_pb2.GameArtifact(schema_version=SCHEMA_VERSION)
    artifact.metadata.game_pk = row["game_pk"]
    artifact.metadata.official_date = _iso_date(row["official_date"])
    artifact.metadata.game_time_utc = _iso_utc(row["game_time_utc"])
    artifact.metadata.away_team_id = row["away_team_id"]
    artifact.metadata.home_team_id = row["home_team_id"]
    artifact.metadata.away_team_name = row["away_team_name"] or ""
    artifact.metadata.home_team_name = row["home_team_name"] or ""
    _set_present(
        artifact.metadata,
        away_score=row["away_score"],
        home_score=row["home_score"],
        is_doubleheader=row["is_doubleheader"],
        game_number=row["game_number"],
    )

    appearances = conn.execute(
        """
        SELECT
            pa_id,
            team_id,
            halfInning AS half_inning,
            inning,
            batter_id,
            pitcher_id,
            event,
            eventType AS event_type,
            description,
            rbi,
            awayScore AS away_score,
            homeScore AS home_score,
            isOut AS is_out,
            balls,
            strikes,
            outs
        FROM "2025_game_plate_appearance"
        WHERE game_pk = ?
        ORDER BY pa_id
        """,
        [game_pk],
    )

    appearances_by_id: dict[int, game_artifact_pb2.PlateAppearance] = {}
    for pa_row in _rows_as_dicts(appearances):
        appearance = artifact.plate_appearances.add(
            pa_id=pa_row["pa_id"],
            batting_team_id=pa_row["team_id"],
            half_inning=_half_inning(pa_row["half_inning"]),
            inning=pa_row["inning"],
            batter_id=pa_row["batter_id"],
            pitcher_id=pa_row["pitcher_id"],
            event=pa_row["event"] or "",
            event_type=pa_row["event_type"] or "",
            description=pa_row["description"] or "",
        )
        _set_present(
            appearance,
            rbi=pa_row["rbi"],
            away_score=pa_row["away_score"],
            home_score=pa_row["home_score"],
            is_out=pa_row["is_out"],
            balls=pa_row["balls"],
            strikes=pa_row["strikes"],
            outs=pa_row["outs"],
        )
        appearances_by_id[pa_row["pa_id"]] = appearance

    pitches = conn.execute(
        """
        SELECT
            pa_id,
            pitch_number,
            description,
            code,
            is_in_play,
            is_strike,
            is_ball,
            is_out,
            pitch_type_code,
            pitch_type_desc AS pitch_type_description,
            balls,
            strikes,
            outs,
            pre_balls,
            pre_strikes,
            pre_outs,
            start_speed,
            end_speed,
            zone,
            plate_time,
            extension,
            pX AS plate_x,
            pZ AS plate_z,
            spin_rate,
            bat_speed,
            is_sword_swing,
            launch_speed,
            launch_angle,
            total_distance,
            trajectory,
            hardness,
            hit_location,
            hit_coord_x AS hit_coordinate_x,
            hit_coord_y AS hit_coordinate_y,
            hit_probability
        FROM pa_plate_events
        WHERE game_pk = ?
        ORDER BY pa_id, pitch_number
        """,
        [game_pk],
    )
    for pitch_row in _rows_as_dicts(pitches):
        pa_id = pitch_row.pop("pa_id")
        try:
            appearance = appearances_by_id[pa_id]
        except KeyError as error:
            raise ValueError(
                f"Pitch {pitch_row['pitch_number']} references missing PA {pa_id}."
            ) from error

        required = {
            "pitch_number": pitch_row.pop("pitch_number"),
            "description": pitch_row.pop("description") or "",
            "code": pitch_row.pop("code") or "",
            "pitch_type_code": pitch_row.pop("pitch_type_code") or "",
            "pitch_type_description": pitch_row.pop("pitch_type_description") or "",
            "trajectory": pitch_row.pop("trajectory") or "",
            "hardness": pitch_row.pop("hardness") or "",
            "hit_location": pitch_row.pop("hit_location") or "",
        }
        pitch = appearance.pitches.add(**required)
        _set_present(pitch, **pitch_row)

    return artifact


def serialize_game(conn: duckdb.DuckDBPyConnection, game_pk: int) -> bytes:
    """Serialize deterministically so checksums are reproducible."""
    return load_game_artifact(conn, game_pk).SerializeToString(deterministic=True)


def deserialize_game(payload: bytes) -> game_artifact_pb2.GameArtifact:
    """Decode through protoc-generated code; no hand-written wire parser is used."""
    return game_artifact_pb2.GameArtifact.FromString(payload)


def write_game_artifact(database: Path, game_pk: int, output: Path) -> int:
    """Export one game and return its serialized byte count."""
    with duckdb.connect(str(database), read_only=True) as conn:
        payload = serialize_game(conn, game_pk)
    output.write_bytes(payload)
    return len(payload)
