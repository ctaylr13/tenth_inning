import { useEffect, useState } from "react";

import { classify, unknownFailure, type ApiError, type Failure } from "./errors";

export type Inning = {
    inning_num: number;
    ordinalNum: string;
    home_runs: number | null;
    home_hits: number | null;
    home_errors: number | null;
    home_leftOnBase: number | null;
    away_runs: number | null;
    away_hits: number | null;
    away_errors: number | null;
    away_leftOnBase: number | null;
};

/** The events the server sends once the stream is open. */
type OpenEvent = { gamePk: number; request_id: string };
type InningEvent = { gamePk: number; seq: number; inning: Inning };
type EndEvent = { gamePk: number; innings: number };
type FailureEvent = { gamePk: number; error: ApiError };

export type LiveStatus = "connecting" | "live" | "done";

export type LiveGame = {
    innings: Inning[];
    status: LiveStatus;
    /** Set only when the feed broke. `done` with no failure is an empty state. */
    failure: Failure | null;
    /** Per-CONNECTION, not per-request -- one id covers the whole session. */
    requestId: string | null;
};

/** Held as one object so switching games is a single reset, not four. */
type State = LiveGame & { gamePk: number | null };

const initial = (gamePk: number | null): State => ({
    gamePk,
    innings: [],
    status: "connecting",
    failure: null,
    requestId: null,
});

const parse = <T,>(event: Event): T | null => {
    try {
        return JSON.parse((event as MessageEvent).data) as T;
    } catch {
        return null;
    }
};

/**
 * Subscribe to one game's replayed inning feed over SSE. No reconnect, backoff,
 * or heartbeats here -- EventSource does all three, which is most of the
 * argument for SSE on a read-only feed.
 */
export const useLiveGame = (gamePk: number | null): LiveGame => {
    const [state, setState] = useState<State>(() => initial(gamePk));

    // Reset during render, so a new game never paints with the old one's
    // innings. Object.is, not !== -- NaN !== NaN would re-set on every render.
    if (!Object.is(state.gamePk, gamePk)) setState(initial(gamePk));

    useEffect(() => {
        if (gamePk === null) return;

        // Relative through the Vite proxy, same as every other call.
        const es = new EventSource(`/api/live/${gamePk}`);

        es.addEventListener("open", (event) => {
            const data = parse<OpenEvent>(event);
            // `open` starts a feed, never resumes one -- EventSource
            // reconnects on its own and the server replays from inning 1.
            setState((prev) => ({
                ...prev,
                innings: [],
                status: "live",
                requestId: data?.request_id ?? null,
            }));
        });

        es.addEventListener("inning", (event) => {
            const data = parse<InningEvent>(event);
            if (!data) return;
            setState((prev) => ({
                ...prev,
                innings: [...prev.innings, data.inning],
            }));
        });

        es.addEventListener("end", (event) => {
            // The server's count is the authority. Zero is an empty state,
            // not an error.
            const data = parse<EndEvent>(event);
            setState((prev) => ({
                ...prev,
                innings: data?.innings === 0 ? [] : prev.innings,
                status: "done",
            }));
            es.close();
        });

        // Named `failure`, not `error`: EventSource fires its own `error` event
        // on connection loss, and both would land on this same listener.
        es.addEventListener("failure", (event) => {
            const data = parse<FailureEvent>(event);
            setState((prev) => ({
                ...prev,
                failure: data ? classify(data.error) : unknownFailure(),
                status: "done",
            }));
            es.close();
        });

        es.addEventListener("error", () => {
            // No envelope -- the connection dropped before any body. An open
            // socket means EventSource is still retrying, not a failure.
            const givenUp = es.readyState === EventSource.CLOSED;
            setState((prev) => ({
                ...prev,
                failure: givenUp
                    ? unknownFailure("DATA_SOURCE_UNAVAILABLE")
                    : prev.failure,
                status: givenUp ? "done" : "connecting",
            }));
        });

        return () => es.close();
    }, [gamePk]);

    return state;
};
