import { create, toBinary } from "@bufbuild/protobuf";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
    GAME_ARTIFACT_TABLE_NAMES,
    decodeGameArtifact,
    gameArtifactToArrow,
    getGameArtifactLocation,
    loadGameArtifactIntoDuckDB,
    type ArtifactConnection,
} from "./gameArtifact";
import {
    GameArtifactSchema,
    HalfInning,
} from "../generated/artifacts/game_artifact_pb";

afterEach(() => vi.unstubAllGlobals());

const artifact = create(GameArtifactSchema, {
    schemaVersion: 1,
    metadata: {
        gamePk: 777940n,
        officialDate: "2025-05-13",
        gameTimeUtc: "2025-05-13T22:40:00Z",
        awayTeamId: 110n,
        homeTeamId: 111n,
        awayTeamName: "Twins",
        homeTeamName: "Red Sox",
        homeScore: 6,
    },
    plateAppearances: [
        {
            paId: 1,
            battingTeamId: 110n,
            halfInning: HalfInning.TOP,
            inning: 1,
            batterId: 1n,
            pitcherId: 2n,
            event: "Single",
            eventType: "single",
            description: "A single",
            pitches: [
                {
                    pitchNumber: 1,
                    description: "Called Strike",
                    code: "C",
                    pitchTypeCode: "FF",
                    pitchTypeDescription: "Four-Seam Fastball",
                    startSpeed: 96.2,
                    trajectory: "",
                    hardness: "",
                    hitLocation: "",
                },
            ],
        },
    ],
});

const arrayBuffer = (bytes: Uint8Array): ArrayBuffer =>
    bytes.buffer.slice(
        bytes.byteOffset,
        bytes.byteOffset + bytes.byteLength
    ) as ArrayBuffer;

describe("game artifact browser adapter", () => {
    it("gets the signed artifact location through the API contract", async () => {
        const fetcher = vi.fn(
            async () =>
                new Response(
                    JSON.stringify({ artifact_url: "https://storage.example/signed" })
                )
        );
        vi.stubGlobal("fetch", fetcher);

        await expect(getGameArtifactLocation(777940)).resolves.toEqual({
            status: "ok",
            data: { artifact_url: "https://storage.example/signed" },
        });
        expect(fetcher).toHaveBeenCalledWith("/api/games/777940", undefined);
    });

    it("decodes generated Protobuf and preserves optional scalar absence", () => {
        const decoded = decodeGameArtifact(
            arrayBuffer(toBinary(GameArtifactSchema, artifact))
        );
        const tables = gameArtifactToArrow(decoded);

        expect(decoded.metadata?.gamePk).toBe(777940n);
        expect(tables.metadata.numRows).toBe(1);
        expect(tables.plateAppearances.numRows).toBe(1);
        expect(tables.pitches.numRows).toBe(1);
        expect(tables.metadata.getChild("away_score")?.get(0)).toBeNull();
        expect(tables.metadata.getChild("home_score")?.get(0)).toBe(6);
    });

    it("runs URL to ArrayBuffer to Protobuf to Arrow to DuckDB", async () => {
        const bytes = toBinary(GameArtifactSchema, artifact);
        const fetcher = vi.fn(async () => new Response(bytes)) as typeof fetch;
        const insertArrowTable = vi.fn<
            ArtifactConnection["insertArrowTable"]
        >(async () => undefined);
        const connection = { insertArrowTable } as ArtifactConnection;

        const decoded = await loadGameArtifactIntoDuckDB(
            "https://storage.example/signed",
            connection,
            fetcher
        );

        expect(decoded.$typeName).toBe(
            "tenth_inning.artifacts.v1.GameArtifact"
        );
        expect(fetcher).toHaveBeenCalledWith("https://storage.example/signed");
        expect(insertArrowTable).toHaveBeenCalledTimes(3);
        expect(insertArrowTable.mock.calls.map((call) => call[1])).toEqual([
            { name: GAME_ARTIFACT_TABLE_NAMES.metadata, create: true },
            {
                name: GAME_ARTIFACT_TABLE_NAMES.plateAppearances,
                create: true,
            },
            { name: GAME_ARTIFACT_TABLE_NAMES.pitches, create: true },
        ]);
    });

    it("rejects unsupported schemas before registration", () => {
        const unsupported = create(GameArtifactSchema, {
            schemaVersion: 2,
            metadata: artifact.metadata,
        });

        expect(() =>
            decodeGameArtifact(
                arrayBuffer(toBinary(GameArtifactSchema, unsupported))
            )
        ).toThrow("Unsupported game artifact schema version 2.");
    });
});
