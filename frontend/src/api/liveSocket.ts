import { useEffect, useState } from "react";

import { classify, unknownFailure, type ApiError, type Failure } from "./errors";
import type { Inning, LiveStatus } from "./live";

/** One union with a `type` discriminant -- there is no `event:` line here, so
 * routing is the client's job. */
type Frame =
    | { type: "open"; gamePk: number; request_id: string }
    | { type: "inning"; gamePk: number; seq: number; inning: Inning }
    | { type: "end"; gamePk: number; innings: number }
    | { type: "failure"; gamePk: number; error: ApiError };

export type SocketGame = {
    innings: Inning[];
    status: LiveStatus;
    failure: Failure | null;
    requestId: string | null;
    /** Reconnects spent. EventSource does this silently; here we own it. */
    reconnects: number;
};

type State = SocketGame & { gamePk: number | null };

const initial = (gamePk: number | null): State => ({
    gamePk,
    innings: [],
    status: "connecting",
    failure: null,
    requestId: null,
    reconnects: 0,
});

/**
 * `new WebSocket("/api/live/ws/1")` throws -- there is no relative form, so the
 * absolute URL is ours to build. Dev is http, so the `wss:` branch is never
 * exercised until the first deploy behind TLS.
 */
const socketUrl = (gamePk: number): string => {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${window.location.host}/api/live/ws/${gamePk}`;
};

// EventSource picks these and never tells you which.
const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 8000;
const MAX_RETRIES = 4;

/**
 * Subscribe to one game's replayed inning feed over a websocket. Same frames and
 * same `classify()` as the SSE hook -- the reconnect machinery below is what
 * EventSource did for free.
 */
export const useSocketGame = (gamePk: number | null): SocketGame => {
    const [state, setState] = useState<State>(() => initial(gamePk));

    // Reset during render, so a new game never paints with the old one's
    // innings. Object.is, not !== -- NaN !== NaN would re-set on every render.
    if (!Object.is(state.gamePk, gamePk)) setState(initial(gamePk));

    useEffect(() => {
        if (gamePk === null) return;

        let socket: WebSocket | null = null;
        let retryTimer: ReturnType<typeof setTimeout> | undefined;
        let attempt = 0;
        // A close is expected only after a terminal frame or our teardown.
        let finished = false;
        let unmounted = false;

        const connect = () => {
            socket = new WebSocket(socketUrl(gamePk));

            socket.onmessage = (event) => {
                let frame: Frame;
                try {
                    frame = JSON.parse(event.data as string) as Frame;
                } catch {
                    return;
                }

                switch (frame.type) {
                    case "open":
                        // A reconnect replays from inning 1 rather than
                        // resuming, so the list resets with the connection.
                        attempt = 0;
                        setState((prev) => ({
                            ...prev,
                            innings: [],
                            status: "live",
                            requestId: frame.request_id,
                        }));
                        break;

                    case "inning":
                        setState((prev) => ({
                            ...prev,
                            innings: [...prev.innings, frame.inning],
                        }));
                        break;

                    case "end":
                        // The server's count is the authority. Zero is an empty
                        // state, not an error.
                        finished = true;
                        setState((prev) => ({
                            ...prev,
                            innings: frame.innings === 0 ? [] : prev.innings,
                            status: "done",
                        }));
                        break;

                    case "failure":
                        // Final, not retryable -- and `error.code` is the only
                        // reason we can tell which. The close code cannot.
                        finished = true;
                        setState((prev) => ({
                            ...prev,
                            failure: classify(frame.error),
                            status: "done",
                        }));
                        break;
                }
            };

            // No onerror handler -- the browser hands it an Event with no code,
            // reason or status. Every error is followed by a close anyway.
            socket.onclose = () => {
                if (unmounted || finished) return;

                if (attempt >= MAX_RETRIES) {
                    setState((prev) => ({
                        ...prev,
                        status: "done",
                        failure: unknownFailure("DATA_SOURCE_UNAVAILABLE"),
                    }));
                    return;
                }

                const delay = Math.min(
                    RETRY_BASE_MS * 2 ** attempt,
                    RETRY_MAX_MS
                );
                attempt += 1;
                setState((prev) => ({
                    ...prev,
                    status: "connecting",
                    reconnects: prev.reconnects + 1,
                }));
                retryTimer = setTimeout(connect, delay);
            };
        };

        connect();

        return () => {
            // Before close(), or our own teardown schedules a reconnect.
            unmounted = true;
            clearTimeout(retryTimer);
            socket?.close();
        };
    }, [gamePk]);

    return state;
};
