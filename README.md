# tenth_inning

A Red Sox 2025 season explorer: a DuckDB warehouse built from MLB StatsAPI data, a
FastAPI read layer over it, and a React frontend that renders the schedule and a

---

## Running it

Two terminals. **Terminal 1 — the API:**

```bash
myenv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — the frontend:**

```bash
cd frontend && yarn dev
```

Then open the Vite URL it prints. `/api/*` is proxied to the API, so it's
same-origin and CORS never comes up.

`--host 127.0.0.1` is deliberate: Docker Desktop listens on `*:8000` over IPv6, and
`localhost` can resolve to `::1` and hit Docker instead of the API. Binding and
proxying to `127.0.0.1` keeps both on IPv4.

The DuckDB file (`redsox_25.duckdb`, ~78MB) is gitignored and rebuildable from
`sox_2025/scripts/`. `server.py` fails with an explicit 500 rather than silently
creating an empty database, so a fresh clone tells you what's missing instead of
reporting "table not found" three layers later.

Tests:

```bash
myenv/bin/pytest
```

---

## Local Postgres

Phase 4 splits the data by _shape_: Postgres for anything transactional — many small
reads and writes from many concurrent clients — and DuckDB for the finished season,
which is big scans over immutable rows. This is also what unblocks everything after
it: DuckDB's exclusive single-process file lock means a second process cannot open
`redsox_25.duckdb` even read-only, so no scaling step is reachable until the
transactional data lives in a client/server database.

```bash
cp .env.example .env      # first time only
docker compose up -d
```

`server.py` reads `DATABASE_URL` from `.env` and opens a SQLAlchemy engine,
`pg_engine`. `watch_history` lives here now — schema via Alembic, not
hand-written `CREATE TABLE IF NOT EXISTS`:

```bash
myenv/bin/alembic upgrade head
```

```bash
psql -h 127.0.0.1 -p 5433 -U tenth_inning -d tenth_inning
```

**Port 5433, not 5432.** Homebrew's `postgresql@15` is already listening on 5432 on
this machine, on both `127.0.0.1` and `::1` — the same trap as Docker Desktop holding
`*:8000`. The container publishes `127.0.0.1:5433->5432/tcp`, so which server you
reach is decided by the port and never by name resolution:

|            | Homebrew `postgresql@15`         | This container   |
| ---------- | -------------------------------- | ---------------- |
| Host port  | 5432                             | 5433             |
| Version    | 15.x                             | 17.x             |
| Managed by | `brew services`                  | `docker compose` |
| Belongs to | your machine, predates this repo | `tenth_inning`   |

Inside the container Postgres still binds 5432 — `select inet_server_port()` returns
5432, because the mapping is on the host side. Another container in this compose file
would reach it at `postgres:5432` without touching the published port at all.

Data lives in a named volume (`tenth_inning_pgdata`), so `docker compose down` keeps
it and only `docker compose down -v` deletes it. Verified by writing a row, cycling
the container, and reading it back.

`docker compose ps` reports `healthy` rather than just `Up` because the service has a
`pg_isready` healthcheck — a running container is not the same as a Postgres that is
accepting connections, and that gap is the first boot's cluster initialization.

Tests use a separate `tenth_inning_test` database, not the one above — same reason
DuckDB tests use a throwaway file instead of `redsox_25.duckdb`. One-time setup:

```bash
psql -h 127.0.0.1 -p 5433 -U tenth_inning -d tenth_inning -c "CREATE DATABASE tenth_inning_test;"
DATABASE_URL=postgresql://tenth_inning:tenth_inning@127.0.0.1:5433/tenth_inning_test myenv/bin/alembic upgrade head
```

---

## The error contract

One envelope shape, everywhere:

```json
{
    "error": {
        "code": "...",
        "message": "...",
        "details": {},
        "request_id": "..."
    }
}
```

Three files own it end to end:

| File                                                       | Role                                                                                                                                                                                                                                                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [`errors.py`](errors.py)                                   | Typed `AppError` subclasses, the `ErrorCode` enum, `error_body()` — the single place that knows the envelope's shape — and `failure_frame()`, the same envelope as a message for transports with no status line                                              |
| [`error_handlers.py`](error_handlers.py)                   | Request-ID middleware plus five exception handlers, all required — drop one and a class of failure escapes the envelope. Each only builds an `AppError`; `_deliver` picks the transport, returning a response over HTTP and sending a frame over a websocket |
| [`frontend/src/api/errors.ts`](frontend/src/api/errors.ts) | The client half — switches on `error.code`, never on the message or the status number                                                                                                                                                                        |

The rule the whole thing exists to enforce: **4xx if the client sent something wrong,
5xx if the client was fine and we broke.** The test is whether retrying the identical
request could ever succeed.

The payoff is that `RESOURCE_NOT_FOUND` is an _empty state_ in the UI, not an error
state. That distinction was impossible when every failure was a 500.

---

## Architecture

Diagrams are generated, not drawn — regenerate them after any design change so they
can't drift:

```bash
myenv/bin/python docs/diagrams/live_layer.py
```

Requires Graphviz on PATH (`brew install graphviz`).

### The live layer: three transports, one API instance

Part 3 builds all three side by side so the trade-offs are visible rather than
asserted. Read each column top to bottom.

![Three transports](docs/diagrams/live_layer_transports.png)

Edge colors are consistent across both diagrams: **red** is a cost paid repeatedly,
**green** is the error contract surviving, **orange** is the contract degraded.

What the picture is actually arguing:

-   **Polling** does one full HTTP transaction per client per tick, opening a new DuckDB
    connection each time via `get_conn()`. In exchange, the error contract needs _zero_
    changes — every tick carries its own status code.
-   **SSE** and **websockets** share one ticker per game, which reads the database
    **once for every client watching**, then fans out. Polling costs one read per client
    per tick. That efficiency argument belongs to both live transports equally, which is
    exactly why it is not an argument _for_ websockets.
-   The contract degrades differently in each. SSE keeps it for errors raised before the
    first byte and loses it after — the status code is physically on the wire and
    immutable. Websockets have no status line at all past the handshake, so the envelope
    has to be rebuilt inside message frames at both ends.

#### The part building it actually changed

Part 3b was written expecting to confirm that websockets are worse at everything. One
result came out the other way, and it is only visible from a browser:

**A 404 from the SSE route never reaches the client.** `raise ResourceNotFound(...)`
happens before the first byte, so the response is a real 404 carrying the full
envelope — `curl` sees it, the tests see it, the server logs it. But `EventSource`
**discards the body of any non-200 response**. All the hook gets is an `error` event
and `readyState === CLOSED`, so `/api/live/999999` renders as a generic _"Something
went wrong."_ with no code and no request id.

The websocket route accepts the socket first and sends the same envelope as a frame,
so the browser renders _"No game with gamePk 999999."_ and the request id. Same
server, same error, same envelope — one transport can deliver it to a browser and the
other cannot.

What that costs is real and worth saying out loud: an accepted-then-closed socket is a
`101` on the wire, so every websocket failure looks like a success to proxies,
load balancers and metrics. The status code survives only in the server log:

```
WS /api/live/ws/999999 -> 404 RESOURCE_NOT_FOUND [request_id=45bbdcc2eb5d] No game with gamePk 999999.
```

Adding the transport also forced a **fifth** exception handler, and rewired the
other four. FastAPI's default websocket validation handler rejects the handshake
with close code `1008` and pydantic's raw error list as the reason — internals that
`handle_validation_error` exists to reshape, on a channel the browser cannot read
anyway (a handshake-phase close reaches JavaScript as a bare `1006`).

The rewiring was the part that wasn't obvious. Starlette passes a `WebSocket` where
a `Request` would go, so the existing handlers _are_ reached on a websocket — they
just used to die on `request.method`. Now `_deliver` branches on the connection
type, which means `raise ResourceNotFound(...)` works identically in both live
routes, and a failure the route never anticipated (a missing DuckDB file, an IO
error) arrives as an envelope instead of a dropped socket.

**Conclusion: SSE is still the right answer for a read-only score feed** — reconnect,
backoff and heartbeats are free there and are hand-written code in
[`liveSocket.ts`](frontend/src/api/liveSocket.ts) — but the reason is narrower than
"the contract survives better." It doesn't. It survives _differently_, and on the
before-the-first-byte case it survives worse.

### What actually forces a message bus

![Scale-out](docs/diagrams/live_layer_scaleout.png)

At one API instance, the `dict[int, set[Queue]]` in [`live.py`](live.py) plus a
for-loop **is** the fan-out. That is correct engineering, not a shortcut. Note that
the websocket route did not add a second registry: `live.py` imports neither `fastapi`
nor `duckdb`, so both live transports subscribe to the same ticker.

A bus replaces **the list**, not the for-loop, and only once the list can no longer see
every client — meaning a second process. The realistic trigger in this repo isn't
scale; it's the ingest scripts in `sox_2025/scripts/`, which are _already_ a separate
process and therefore already unable to reach the connection list.

---

## Progress

| Phase   | Scope                                                                                                                      | State       |
| ------- | -------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Part 1  | Error contract: typed errors, one envelope, request-id round trip, five handlers                                           | Done        |
| Part 2  | Read endpoints with real validation — `/api/games`, `/api/games/{gamePk}`, `/api/games/{gamePk}/linescore`                 | Done        |
| Part 3  | Live layer: SSE + REST polling, contrasted side by side (`/api/live/{gamePk}`, `live.py`, `frontend/src/api/live.ts`)      | Done        |
| Part 3b | The websocket version, to feel what it costs (`/api/live/ws/{gamePk}`, `frontend/src/api/liveSocket.ts`)                   | Done        |
| Part 4  | Postgres for transactional state, DuckDB for analytics — `watch_history` moved, via Alembic                               | In progress |
| Part 5  | Deploy: one container, real origins, real HTTPS, a health check                                                            | After 4     |

Open work is tracked in `tdl.txt`, which is gitignored — it's a scratch list, not a
spec.
