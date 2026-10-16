import type { AsyncDuckDBConnection } from "@duckdb/duckdb-wasm";

export type PitchTypeOption = {
    code: string;
    description: string;
};

export type PitchRow = {
    paId: number;
    pitchNumber: number;
    inning: number;
    halfInning: string;
    batterId: string;
    pitcherId: string;
    balls: number | null;
    strikes: number | null;
    pitchTypeCode: string;
    pitchTypeDescription: string;
    startSpeed: number | null;
    description: string;
};

const SELECT_PITCHES = `
    SELECT
        pa.pa_id,
        p.pitch_number,
        pa.inning,
        CASE pa.half_inning
            WHEN 1 THEN 'Top'
            WHEN 2 THEN 'Bottom'
            ELSE 'Unknown'
        END AS half_inning,
        CAST(pa.batter_id AS VARCHAR) AS batter_id,
        CAST(pa.pitcher_id AS VARCHAR) AS pitcher_id,
        p.pre_balls AS balls,
        p.pre_strikes AS strikes,
        p.pitch_type_code,
        p.pitch_type_description,
        p.start_speed,
        p.description
    FROM pitches AS p
    JOIN plate_appearances AS pa USING (game_pk, pa_id)
`;

const ORDER_PITCHES = "ORDER BY pa.pa_id, p.pitch_number";

type ArrowRow = Record<string, unknown>;

const toNumber = (value: unknown): number => Number(value);
const toOptionalNumber = (value: unknown): number | null =>
    value === null || value === undefined ? null : Number(value);
const toString = (value: unknown): string => String(value ?? "");

const mapPitchRow = (row: ArrowRow): PitchRow => ({
    paId: toNumber(row.pa_id),
    pitchNumber: toNumber(row.pitch_number),
    inning: toNumber(row.inning),
    halfInning: toString(row.half_inning),
    batterId: toString(row.batter_id),
    pitcherId: toString(row.pitcher_id),
    balls: toOptionalNumber(row.balls),
    strikes: toOptionalNumber(row.strikes),
    pitchTypeCode: toString(row.pitch_type_code),
    pitchTypeDescription: toString(row.pitch_type_description),
    startSpeed: toOptionalNumber(row.start_speed),
    description: toString(row.description),
});

export const listPitchTypes = async (
    connection: AsyncDuckDBConnection
): Promise<PitchTypeOption[]> => {
    const result = await connection.query(`
        SELECT DISTINCT pitch_type_code, pitch_type_description
        FROM pitches
        WHERE pitch_type_code <> ''
        ORDER BY pitch_type_description, pitch_type_code
    `);

    return result.toArray().map((row) => ({
        code: toString(row.pitch_type_code),
        description: toString(row.pitch_type_description),
    }));
};

export const queryPitches = async (
    connection: AsyncDuckDBConnection,
    pitchTypeCode: string
): Promise<PitchRow[]> => {
    if (!pitchTypeCode) {
        const result = await connection.query(
            `${SELECT_PITCHES} ${ORDER_PITCHES}`
        );
        return result.toArray().map(mapPitchRow);
    }

    const statement = await connection.prepare(
        `${SELECT_PITCHES} WHERE p.pitch_type_code = ? ${ORDER_PITCHES}`
    );
    try {
        const result = await statement.query(pitchTypeCode);
        return result.toArray().map(mapPitchRow);
    } finally {
        await statement.close();
    }
};
