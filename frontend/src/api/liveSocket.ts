import { useEffect, useState } from "react";

import { classify, unknownFailure, type ApiError, type Failure } from "./errors";
import type { Inning, LiveStatus } from "./live";

/**
 * The frames the server sends. One union with a `type` discriminant, because a
 * websocket has no equivalent of SSE's `event:` line -- there is exactly one
 * onmessage handler and routing is the client's job.
 */
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
    /** Reconnects this client has spent. EventSource does this silently and
     * for free; here it is code we own, so it is a number we can show. */
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
 * `new WebSocket("/api/live/ws/1")` throws -- the constructor has no relative
 * form, so the client has to rebuild the absolute URL the browser assembles for
 * free on every other call in this app, scheme included.
 *
 * That scheme swap is the part worth staring at. Dev is http, so `ws:` is
 * always right here and the `wss:` branch is never once exercised until the
 * first deploy behind TLS. Same shape as CORS_ALLOW_ORIGINS in server.py:
 * config that can be wrong for months because nothing local runs it.
 */
export const socketUrl = (gamePk: number): string => {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${window.location.host}/api/live/ws/${gamePk}`;
};

// EventSource picks its own backoff and never tells you what it chose. These
// are the same decision, made in the open.
const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 8000;
const MAX_RETRIES = 4;

/**
 * Subscribe to one game's replayed inning feed over a websocket.
 *
 * Same feed, same frames, same `classify()` as the SSE hook. Everything below
 * the message handler is what SSE got for free: URL assembly, reconnect,
 * backoff, giving up, and deciding which failures are even worth retrying.
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
        // A close is only expected after a terminal frame or our own teardown.
        // Anything else is a drop, and drops are the thing to reconnect from.
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
                        // resuming -- the ticker has no idea we were here
                        // before -- so the list resets with the connection.
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
                        // The payoff for hand-delivering the envelope. This
                        // close is final rather than something to retry, and
                        // the only reason we can know that is `error.code` --
                        // the close code alone cannot tell "no such game" from
                        // "the database blinked".
                        finished = true;
                        setState((prev) => ({
                            ...prev,
                            failure: classify(frame.error),
                            status: "done",
                        }));
                        break;
                }
            };

            // No onerror handler: the browser hands it an Event with no code,
            // no reason and no status, deliberately, so a page cannot probe the
            // network it is on. Every error is followed by a close, so close is
            // the only place a decision can actually be made.
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
            // Order matters: the flag has to be set before close(), or our own
            // teardown fires onclose and schedules a reconnect to nowhere.
            unmounted = true;
            clearTimeout(retryTimer);
            socket?.close();
        };
    }, [gamePk]);

    return state;
};
