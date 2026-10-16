import type { AsyncDuckDBConnection } from "@duckdb/duckdb-wasm";
import { tableFromArrays } from "apache-arrow";
import { describe, expect, it, vi } from "vitest";

import { listPitchTypes, queryPitches } from "./pitchTable";

const pitchTable = tableFromArrays({
    pa_id: [0],
    pitch_number: [1],
    inning: [1],
    half_inning: ["Top"],
    batter_id: ["680776"],
    pitcher_id: ["663947"],
    balls: [0],
    strikes: [0],
    pitch_type_code: ["FF"],
    pitch_type_description: ["Four-Seam Fastball"],
    start_speed: [96.2],
    description: ["Called Strike"],
});

describe("pitch table SQL", () => {
    it("lists the pitch types present in the artifact", async () => {
        const query = vi.fn(async (sql: string) => {
            expect(sql).toContain("SELECT DISTINCT pitch_type_code");
            return tableFromArrays({
                pitch_type_code: ["FF"],
                pitch_type_description: ["Four-Seam Fastball"],
            });
        });
        const connection = { query } as unknown as AsyncDuckDBConnection;

        await expect(listPitchTypes(connection)).resolves.toEqual([
            { code: "FF", description: "Four-Seam Fastball" },
        ]);
        expect(query).toHaveBeenCalledOnce();
    });

    it("binds the selected pitch type in the DuckDB query", async () => {
        const statementQuery = vi.fn(async () => pitchTable);
        const close = vi.fn(async () => undefined);
        const prepare = vi.fn(async (sql: string) => {
            expect(sql).toContain("WHERE p.pitch_type_code = ?");
            return { query: statementQuery, close };
        });
        const connection = { prepare } as unknown as AsyncDuckDBConnection;

        const rows = await queryPitches(connection, "FF");

        expect(prepare).toHaveBeenCalledOnce();
        expect(statementQuery).toHaveBeenCalledWith("FF");
        expect(close).toHaveBeenCalledOnce();
        expect(rows[0]).toMatchObject({
            pitchTypeCode: "FF",
            startSpeed: 96.2,
            batterId: "680776",
        });
    });
});
