import * as duckdb from "@duckdb/duckdb-wasm";
import duckdbWasmEh from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import ehWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import mvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbWasmMvp from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";

import { loadGameArtifactIntoDuckDB } from "./gameArtifact";

const BUNDLES: duckdb.DuckDBBundles = {
    mvp: {
        mainModule: duckdbWasmMvp,
        mainWorker: mvpWorker,
    },
    eh: {
        mainModule: duckdbWasmEh,
        mainWorker: ehWorker,
    },
};

export type GameArtifactDatabase = {
    connection: duckdb.AsyncDuckDBConnection;
    close: () => Promise<void>;
};

export const openGameArtifactDatabase = async (
    signedUrl: string
): Promise<GameArtifactDatabase> => {
    const bundle = await duckdb.selectBundle(BUNDLES);
    if (!bundle.mainWorker) {
        throw new Error("This browser cannot start the game database.");
    }

    const worker = new Worker(bundle.mainWorker);
    const database = new duckdb.AsyncDuckDB(
        new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING),
        worker
    );
    let connection: duckdb.AsyncDuckDBConnection | null = null;

    try {
        await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
        const openConnection = await database.connect();
        connection = openConnection;
        await loadGameArtifactIntoDuckDB(signedUrl, openConnection);
        let closed = false;

        return {
            connection: openConnection,
            close: async () => {
                if (closed) return;
                closed = true;
                try {
                    await openConnection.close();
                } finally {
                    await database.terminate();
                }
            },
        };
    } catch (error) {
        try {
            await connection?.close();
        } finally {
            await database.terminate();
        }
        throw error;
    }
};
