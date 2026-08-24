import { useEffect, useState } from "react";

import { request, type Failure } from "./errors";
import type { Inning } from "./live";

export type PolledGame = {
    innings: Inning[];
    failure: Failure | null;
    /** How many HTTP round trips this client has spent. The whole point. */
    requests: number;
};

type LinescoreResponse = { gamePk: number; innings: Inning[] };

type State = PolledGame & { gamePk: number | null };

export const POLL_INTERVAL_MS = 1000;

const initial = (gamePk: number | null): State => ({
    gamePk,
    innings: [],
    failure: null,
    requests: 0,
});

/**
 * The baseline the live layer is measured against. Every tick is a whole HTTP
 * transaction, so `request()` and the error contract work unchanged -- the cost
 * is the `requests` counter, which climbs forever for identical data.
 */
export const usePolledGame = (
    gamePk: number | null,
    intervalMs: number = POLL_INTERVAL_MS
): PolledGame => {
    const [state, setState] = useState<State>(() => initial(gamePk));

    // Object.is, not !== -- NaN !== NaN would re-set on every render.
    if (!Object.is(state.gamePk, gamePk)) setState(initial(gamePk));

    useEffect(() => {
        if (gamePk === null) return;

        // A late response must not overwrite a newer game's data.
        let cancelled = false;

        const tick = async () => {
            setState((prev) => ({ ...prev, requests: prev.requests + 1 }));

            const res = await request<LinescoreResponse>(
                `/api/games/${gamePk}/linescore`
            );
            if (cancelled) return;

            setState((prev) =>
                res.status === "ok"
                    ? { ...prev, innings: res.data.innings, failure: null }
                    : { ...prev, failure: res }
            );
        };

        void tick();
        const id = setInterval(() => void tick(), intervalMs);

        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [gamePk, intervalMs]);

    return state;
};
