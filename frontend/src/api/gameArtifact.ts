import { fromBinary } from "@bufbuild/protobuf";
import type { AsyncDuckDBConnection } from "@duckdb/duckdb-wasm";
import {
    Bool,
    Float64,
    Table,
    Uint32,
    Uint64,
    Utf8,
    vectorFromArray,
} from "apache-arrow";

import {
    GameArtifactSchema,
    type GameArtifact,
} from "../generated/artifacts/game_artifact_pb";

export const GAME_ARTIFACT_SCHEMA_VERSION = 1;

const DOWNLOAD_FAILED = "The game artifact could not be downloaded.";
const MISSING_METADATA = "The game artifact has no metadata.";

export const GAME_ARTIFACT_TABLE_NAMES = {
    metadata: "game_metadata",
    plateAppearances: "plate_appearances",
    pitches: "pitches",
} as const;

export type GameArtifactArrowTables = {
    metadata: Table;
    plateAppearances: Table;
    pitches: Table;
};

export type ArtifactConnection = Pick<
    AsyncDuckDBConnection,
    "insertArrowTable"
>;

type Optional<T> = T | null | undefined;

const nullable = <T,>(values: readonly Optional<T>[]): (T | null)[] =>
    values.map((value) => value ?? null);

const uint32Vector = (values: readonly Optional<number>[]) =>
    vectorFromArray(nullable(values), new Uint32());

const uint64Vector = (values: readonly Optional<bigint>[]) =>
    vectorFromArray(nullable(values), new Uint64());

const float64Vector = (values: readonly Optional<number>[]) =>
    vectorFromArray(nullable(values), new Float64());

const booleanVector = (values: readonly Optional<boolean>[]) =>
    vectorFromArray(nullable(values), new Bool());

const stringVector = (values: readonly Optional<string>[]) =>
    vectorFromArray(nullable(values), new Utf8());

export const fetchGameArtifact = async (
    signedUrl: string,
    fetcher: typeof fetch = fetch
): Promise<ArrayBuffer> => {
    if (!signedUrl) throw new Error("The artifact URL is missing.");

    let response: Response;
    try {
        response = await fetcher(signedUrl);
    } catch (cause) {
        throw new Error(DOWNLOAD_FAILED, { cause });
    }

    if (!response.ok) {
        throw new Error(
            `The game artifact download failed with HTTP ${response.status}.`
        );
    }

    try {
        return await response.arrayBuffer();
    } catch (cause) {
        throw new Error(DOWNLOAD_FAILED, { cause });
    }
};

export const decodeGameArtifact = (buffer: ArrayBuffer): GameArtifact => {
    let artifact: GameArtifact;
    try {
        artifact = fromBinary(GameArtifactSchema, new Uint8Array(buffer));
    } catch (cause) {
        throw new Error("The game artifact is not valid Protobuf.", { cause });
    }

    if (artifact.schemaVersion !== GAME_ARTIFACT_SCHEMA_VERSION) {
        throw new Error(
            `Unsupported game artifact schema version ${artifact.schemaVersion}.`
        );
    }
    if (!artifact.metadata) {
        throw new Error(MISSING_METADATA);
    }

    return artifact;
};

export const gameArtifactToArrow = (
    artifact: GameArtifact
): GameArtifactArrowTables => {
    const metadata = artifact.metadata;
    if (!metadata) throw new Error(MISSING_METADATA);

    const appearances = artifact.plateAppearances;
    const pitchRows = appearances.flatMap((appearance) =>
        appearance.pitches.map((pitch) => ({
            gamePk: metadata.gamePk,
            paId: appearance.paId,
            pitch,
        }))
    );

    return {
        metadata: new Table({
            schema_version: uint32Vector([artifact.schemaVersion]),
            game_pk: uint64Vector([metadata.gamePk]),
            official_date: stringVector([metadata.officialDate]),
            game_time_utc: stringVector([metadata.gameTimeUtc]),
            away_team_id: uint64Vector([metadata.awayTeamId]),
            home_team_id: uint64Vector([metadata.homeTeamId]),
            away_team_name: stringVector([metadata.awayTeamName]),
            home_team_name: stringVector([metadata.homeTeamName]),
            away_score: uint32Vector([metadata.awayScore]),
            home_score: uint32Vector([metadata.homeScore]),
            is_doubleheader: booleanVector([metadata.isDoubleheader]),
            game_number: uint32Vector([metadata.gameNumber]),
        }),
        plateAppearances: new Table({
            game_pk: uint64Vector(appearances.map(() => metadata.gamePk)),
            pa_id: uint32Vector(appearances.map((row) => row.paId)),
            batting_team_id: uint64Vector(
                appearances.map((row) => row.battingTeamId)
            ),
            half_inning: uint32Vector(
                appearances.map((row) => row.halfInning)
            ),
            inning: uint32Vector(appearances.map((row) => row.inning)),
            batter_id: uint64Vector(appearances.map((row) => row.batterId)),
            pitcher_id: uint64Vector(appearances.map((row) => row.pitcherId)),
            event: stringVector(appearances.map((row) => row.event)),
            event_type: stringVector(appearances.map((row) => row.eventType)),
            description: stringVector(
                appearances.map((row) => row.description)
            ),
            rbi: uint32Vector(appearances.map((row) => row.rbi)),
            away_score: uint32Vector(
                appearances.map((row) => row.awayScore)
            ),
            home_score: uint32Vector(
                appearances.map((row) => row.homeScore)
            ),
            is_out: booleanVector(appearances.map((row) => row.isOut)),
            balls: uint32Vector(appearances.map((row) => row.balls)),
            strikes: uint32Vector(appearances.map((row) => row.strikes)),
            outs: uint32Vector(appearances.map((row) => row.outs)),
        }),
        pitches: new Table({
            game_pk: uint64Vector(pitchRows.map((row) => row.gamePk)),
            pa_id: uint32Vector(pitchRows.map((row) => row.paId)),
            pitch_number: uint32Vector(
                pitchRows.map((row) => row.pitch.pitchNumber)
            ),
            description: stringVector(
                pitchRows.map((row) => row.pitch.description)
            ),
            code: stringVector(pitchRows.map((row) => row.pitch.code)),
            is_in_play: booleanVector(
                pitchRows.map((row) => row.pitch.isInPlay)
            ),
            is_strike: booleanVector(
                pitchRows.map((row) => row.pitch.isStrike)
            ),
            is_ball: booleanVector(pitchRows.map((row) => row.pitch.isBall)),
            is_out: booleanVector(pitchRows.map((row) => row.pitch.isOut)),
            pitch_type_code: stringVector(
                pitchRows.map((row) => row.pitch.pitchTypeCode)
            ),
            pitch_type_description: stringVector(
                pitchRows.map((row) => row.pitch.pitchTypeDescription)
            ),
            balls: uint32Vector(pitchRows.map((row) => row.pitch.balls)),
            strikes: uint32Vector(pitchRows.map((row) => row.pitch.strikes)),
            outs: uint32Vector(pitchRows.map((row) => row.pitch.outs)),
            pre_balls: uint32Vector(pitchRows.map((row) => row.pitch.preBalls)),
            pre_strikes: uint32Vector(
                pitchRows.map((row) => row.pitch.preStrikes)
            ),
            pre_outs: uint32Vector(pitchRows.map((row) => row.pitch.preOuts)),
            start_speed: float64Vector(
                pitchRows.map((row) => row.pitch.startSpeed)
            ),
            end_speed: float64Vector(
                pitchRows.map((row) => row.pitch.endSpeed)
            ),
            zone: uint32Vector(pitchRows.map((row) => row.pitch.zone)),
            plate_time: float64Vector(
                pitchRows.map((row) => row.pitch.plateTime)
            ),
            extension: float64Vector(
                pitchRows.map((row) => row.pitch.extension)
            ),
            plate_x: float64Vector(pitchRows.map((row) => row.pitch.plateX)),
            plate_z: float64Vector(pitchRows.map((row) => row.pitch.plateZ)),
            spin_rate: uint32Vector(
                pitchRows.map((row) => row.pitch.spinRate)
            ),
            bat_speed: float64Vector(
                pitchRows.map((row) => row.pitch.batSpeed)
            ),
            is_sword_swing: booleanVector(
                pitchRows.map((row) => row.pitch.isSwordSwing)
            ),
            launch_speed: float64Vector(
                pitchRows.map((row) => row.pitch.launchSpeed)
            ),
            launch_angle: float64Vector(
                pitchRows.map((row) => row.pitch.launchAngle)
            ),
            total_distance: float64Vector(
                pitchRows.map((row) => row.pitch.totalDistance)
            ),
            trajectory: stringVector(
                pitchRows.map((row) => row.pitch.trajectory)
            ),
            hardness: stringVector(
                pitchRows.map((row) => row.pitch.hardness)
            ),
            hit_location: stringVector(
                pitchRows.map((row) => row.pitch.hitLocation)
            ),
            hit_coordinate_x: float64Vector(
                pitchRows.map((row) => row.pitch.hitCoordinateX)
            ),
            hit_coordinate_y: float64Vector(
                pitchRows.map((row) => row.pitch.hitCoordinateY)
            ),
            hit_probability: float64Vector(
                pitchRows.map((row) => row.pitch.hitProbability)
            ),
        }),
    };
};

export const registerGameArtifactTables = async (
    connection: ArtifactConnection,
    tables: GameArtifactArrowTables
): Promise<void> => {
    const registrations = [
        [GAME_ARTIFACT_TABLE_NAMES.metadata, tables.metadata],
        [GAME_ARTIFACT_TABLE_NAMES.plateAppearances, tables.plateAppearances],
        [GAME_ARTIFACT_TABLE_NAMES.pitches, tables.pitches],
    ] as const;

    for (const [name, table] of registrations) {
        await connection.insertArrowTable(table, { name, create: true });
    }
};

export const loadGameArtifactIntoDuckDB = async (
    signedUrl: string,
    connection: ArtifactConnection,
    fetcher: typeof fetch = fetch
): Promise<GameArtifact> => {
    const buffer = await fetchGameArtifact(signedUrl, fetcher);
    const artifact = decodeGameArtifact(buffer);
    const tables = gameArtifactToArrow(artifact);
    await registerGameArtifactTables(connection, tables);
    return artifact;
};
