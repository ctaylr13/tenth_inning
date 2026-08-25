import asyncio
import json
import logging
import os
import uuid
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import duckdb
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi import Path as FastPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from error_handlers import (
    WS_INTERNAL_ERROR,
    WS_NORMAL_CLOSURE,
    get_request_id,
    install_error_handling,
)
from errors import (
    FAILURE_TYPE,
    DataSourceUnavailable,
    DuplicateWatchEntry,
    InternalError,
    ResourceNotFound,
    ValidationFailed,
)
from live import END_TYPE, TERMINAL_TYPES, Broadcaster

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DB_PATH = "redsox_25.duckdb"  # optional: make absolute
SCHEDULE_TABLE = 'main."2025_schedule"'
GAME_INFO_TABLE = 'main."2025_game_info"'
LINESCORE_TABLE = 'main."line_score_innings"'


# `or` not .get()'s default -- empty string is falsy but present, and would
# otherwise skip the fallback and crash create_engine() at import.
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or "postgresql://tenth_inning:tenth_inning@127.0.0.1:5433/tenth_inning"
)

pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class WatchRow(BaseModel):
    gamePk: int
    watched: bool


app = FastAPI()
install_error_handling(app)


DEV_ORIGINS = ["http://localhost:5173", "http://localhost:5174"]
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", ",".join(DEV_ORIGINS)).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

logger = logging.getLogger("tenth_inning")


def _watched_true_pks() -> set[int]:
    """gamePks with watched=TRUE in Postgres. Not present means False."""
    try:
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text('SELECT "gamePk" FROM watch_history WHERE watched')
            )
            return {row[0] for row in rows}
    except OperationalError as e:
        raise DataSourceUnavailable() from e
    except ProgrammingError as e:
        raise InternalError("A required table is missing from the database.") from e


def get_conn():
    # duckdb.connect() creates a missing file instead of raising -- without
    if not Path(DB_PATH).exists():
        raise InternalError(f"Database file {DB_PATH!r} is missing.")
    try:
        return duckdb.connect(DB_PATH)
    except duckdb.IOException as e:
        raise DataSourceUnavailable() from e


def _rows(conn, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run a read and hand back JSON-safe dicts. NaN/NaT become null."""
    df = conn.execute(sql, params or []).fetchdf()
    return df.where(pd.notnull(df), None).to_dict(orient="records")


def _read(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Every read route's body: one query, the same three failure branches."""
    conn = get_conn()
    try:
        return _rows(conn, sql, params)
    except duckdb.CatalogException as e:
        # Our schema is broken, not their request.
        raise InternalError("A required table is missing from the database.") from e
    except duckdb.IOException as e:
        raise DataSourceUnavailable() from e
    finally:
        conn.close()


class GameResult(str, Enum):
    """Filter values for /api/games. An unknown one is a 422, not a silent
    empty list -- the client asked something we don't answer."""

    win = "win"
    loss = "loss"


# The season runs late March to late September, so a month outside 3..9 is a
# client bug rather than a legitimately empty result.
SEASON_FIRST_MONTH = 3
SEASON_LAST_MONTH = 9


@app.get("/api/games")
def list_games(
    month: Annotated[
        int | None,
        Query(
            ge=SEASON_FIRST_MONTH,
            le=SEASON_LAST_MONTH,
            description="Calendar month of the official date, 3-9.",
        ),
    ] = None,
    result: Annotated[
        GameResult | None, Query(description="Only games the Sox won or lost.")
    ] = None,
    watched: Annotated[
        bool | None, Query(description="Filter by watch-history state.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """The schedule, filtered and paged.

    Values are bound as parameters, never interpolated -- validation decides
    whether a request is answerable, it is not what keeps the SQL safe.
    """
    # watched can't be a SQL join across two engines -- fetched once instead.
    watched_pks = _watched_true_pks()

    where, params = ["1 = 1"], []
    if month is not None:
        where.append("MONTH(s.officialDate) = ?")
        params.append(month)
    if result is not None:
        where.append("s.sox_is_winner = ?")
        params.append(result is GameResult.win)
    if watched is not None:
        if watched_pks:
            placeholders = ",".join("?" for _ in watched_pks)
            op = "IN" if watched else "NOT IN"
            where.append(f"s.gamePk {op} ({placeholders})")
            params.extend(watched_pks)
        elif watched:
            # Nothing is watched, so "watched=true" matches nothing.
            where.append("1 = 0")
        # else: nothing is watched, so "watched=false" already matches everything.
    clause = " AND ".join(where)

    joined = f"FROM {SCHEDULE_TABLE} s WHERE {clause}"

    total = _read(f"SELECT COUNT(*) AS n {joined}", params)[0]["n"]
    items = _read(
        f"""
        SELECT s.gamePk,
               s.gameDate::VARCHAR AS gameDate,
               s.officialDate::VARCHAR AS officialDate,
               s.doubleheader,
               s.home_score, s.away_score, s.sox_is_winner
        {joined}
        ORDER BY s.gameDate
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    for item in items:
        item["watched"] = item["gamePk"] in watched_pks
    # A filter that matches nothing is an empty page, not an error.
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


@app.get("/api/games/{gamePk}")
def get_game(gamePk: Annotated[int, FastPath(gt=0)]) -> dict[str, Any]:
    """One game. A gamePk that parses but doesn't exist is a 404, not a 422."""
    rows = _read(
        f"""
        SELECT g.*, s.gameDate::VARCHAR AS gameDate, s.doubleheader
        FROM {GAME_INFO_TABLE} g
        JOIN {SCHEDULE_TABLE} s USING (gamePk)
        WHERE g.gamePk = ?
        """,
        [gamePk],
    )
    if not rows:
        raise ResourceNotFound(f"No game with gamePk {gamePk}.", gamePk=gamePk)
    row = rows[0]
    row["watched"] = gamePk in _watched_true_pks()
    return row


def _load_innings(gamePk: int) -> list[dict[str, Any]]:
    """The one inning query. Shared by the linescore route and the replay ticker
    so a column added in one place cannot go missing in the other."""
    return _read(
        f"""
        SELECT inning_num, ordinalNum,
               home_runs, home_hits, home_errors, home_leftOnBase,
               away_runs, away_hits, away_errors, away_leftOnBase
        FROM {LINESCORE_TABLE}
        WHERE gamePk = ?
        ORDER BY inning_num
        """,
        [gamePk],
    )


@app.get("/api/games/{gamePk}/linescore")
def get_linescore(gamePk: Annotated[int, FastPath(gt=0)]) -> dict[str, Any]:
    """Inning-by-inning for one game.

    A real game with no innings recorded still 404s on the game check above, so
    an empty innings list means the game exists and wasn't played.
    """
    if not _read(f"SELECT 1 FROM {SCHEDULE_TABLE} WHERE gamePk = ? LIMIT 1", [gamePk]):
        raise ResourceNotFound(f"No game with gamePk {gamePk}.", gamePk=gamePk)

    return {"gamePk": gamePk, "innings": _load_innings(gamePk)}


# the live layer -- see live.py for the fan-out, README.md for why SSE
broadcaster = Broadcaster(_load_innings)


def _sse(event: str, payload: dict[str, Any]) -> str:
    """One SSE frame. The trailing blank line terminates it -- without it the
    browser buffers forever."""
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.get("/api/live/{gamePk}")
async def stream_game(
    request: Request, gamePk: Annotated[int, FastPath(gt=0)]
) -> StreamingResponse:
    """Replay one game's innings as Server-Sent Events.
    `async def` because subscribing starts an asyncio task, and a sync route runs
    in a threadpool with no running loop. The existence check is here rather than
    in the generator because the status code is committed at the first byte --
    past it a raise is a RuntimeError, not a 404."""
    exists = await asyncio.to_thread(
        _read, f"SELECT 1 FROM {SCHEDULE_TABLE} WHERE gamePk = ? LIMIT 1", [gamePk]
    )
    if not exists:
        raise ResourceNotFound(f"No game with gamePk {gamePk}.", gamePk=gamePk)

    request_id = get_request_id(request)
    queue = broadcaster.subscribe(gamePk)

    async def frames():
        """Must never raise -- past the first byte no handler is left, so a
        failure has to arrive as an event like any other."""
        try:
            yield _sse("open", {"gamePk": gamePk, "request_id": request_id})
            while True:
                message = await queue.get()
                yield _sse(message["type"], message)
                if message["type"] in TERMINAL_TYPES:
                    return
        finally:
            # Runs on client disconnect too, which is what stops an abandoned
            # ticker.
            broadcaster.unsubscribe(gamePk, queue)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx buffers proxied responses by default, holding every event
            # until the stream ends.
            "X-Accel-Buffering": "no",
        },
    )


# the same feed over websockets -- same ticker, same errors, no status line
# The handlers reach a websocket scope too (Starlette passes a WebSocket where a
# Request would be), so `raise` still works here -- _deliver just puts the
# envelope in a frame instead of a response. What does NOT reach it is
# RequestIDMiddleware, which is a BaseHTTPMiddleware and only wraps "http".

# Keyed off the constants, not the literals -- rename one and this must follow.
WS_CLOSE_CODES = {END_TYPE: WS_NORMAL_CLOSURE, FAILURE_TYPE: WS_INTERNAL_ERROR}


async def _ws_send(websocket: WebSocket, message: dict[str, Any]) -> None:
    """One frame. Same `default=str` as _sse -- the transports must not disagree
    about how a stray date serializes."""
    await websocket.send_text(json.dumps(message, default=str))


async def _ws_wait_for_disconnect(websocket: WebSocket) -> None:
    """Notice the client leaving. SSE gets this free when the ASGI server
    cancels its generator; a send-only socket loop is parked on queue.get() and
    nothing wakes it, so an abandoned ticker would run on."""
    try:
        while True:
            if (await websocket.receive())["type"] == "websocket.disconnect":
                return
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: receive() after the disconnect was already consumed.
        return


@app.websocket("/api/live/ws/{gamePk}")
async def stream_game_ws(
    websocket: WebSocket, gamePk: Annotated[int, FastPath(gt=0)]
) -> None:
    """Replay one game's innings over a websocket.

    Accept before reading, not after. A rejected handshake reaches JavaScript as
    a bare close with no status and no body, so the client could not tell "no
    such game" from "the API is down". Accepting costs the status line -- every
    failure now looks like a 101 on the wire -- and buys back the envelope."""
    # No middleware ran, so mint the id here and park it where _close_with_error
    # will find it: one connection, one id, whether it ends well or badly.
    request_id = uuid.uuid4().hex[:12]
    websocket.state.request_id = request_id
    await websocket.accept()

    # Raised, not hand-delivered -- identical to the SSE route above, because
    # the handler now knows how to answer a websocket. Anything else this read
    # can raise (missing file, IO error, missing table) takes the same path.
    exists = await asyncio.to_thread(
        _read, f"SELECT 1 FROM {SCHEDULE_TABLE} WHERE gamePk = ? LIMIT 1", [gamePk]
    )
    if not exists:
        raise ResourceNotFound(f"No game with gamePk {gamePk}.", gamePk=gamePk)

    queue = broadcaster.subscribe(gamePk)
    # Before the first send, so a client that vanishes mid-handshake is noticed.
    reader = asyncio.create_task(_ws_wait_for_disconnect(websocket))

    try:
        await _ws_send(
            websocket, {"type": "open", "gamePk": gamePk, "request_id": request_id}
        )

        while True:
            pending = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait(
                {pending, reader}, return_when=asyncio.FIRST_COMPLETED
            )
            if reader in done:
                pending.cancel()
                return

            message = pending.result()
            await _ws_send(websocket, message)
            if message["type"] in TERMINAL_TYPES:
                # Explicit, or Starlette picks the code instead.
                await websocket.close(code=WS_CLOSE_CODES[message["type"]])
                return
    except WebSocketDisconnect:
        # The client left between the wait and the send.
        return
    finally:
        reader.cancel()
        # Same guarantee as the SSE generator's finally.
        broadcaster.unsubscribe(gamePk, queue)


@app.get("/api/schedule")
def get_schedule() -> list[dict[str, Any]]:
    # DuckDB first, so a broken schedule fails before touching Postgres.
    items = _read(f"""
        SELECT s.gamePk,
               s.gameDate::VARCHAR AS gameDate,
               s.officialDate::VARCHAR AS officialDate,
               s.doubleheader
        FROM {SCHEDULE_TABLE} s
        ORDER BY s.gameDate
    """)
    watched_pks = _watched_true_pks()
    for item in items:
        item["watched"] = item["gamePk"] in watched_pks
    # Zero games is an empty state: 200 [], never 204 -- [] is a body.
    return items


UPSERT_WATCHED = text("""
    INSERT INTO watch_history ("gamePk", watched)
    VALUES (:gamePk, :watched)
    ON CONFLICT ("gamePk") DO UPDATE SET watched = EXCLUDED.watched
""")


@app.put("/api/watchhistory")
def update_watchhistory(rows: list[WatchRow]):
    if not rows:
        # 400 not 422: the body parsed, it just carries nothing to do.
        raise ValidationFailed("No rows provided.", status_code=400)

    duplicates = sorted(
        pk for pk, n in Counter(r.gamePk for r in rows).items() if n > 1
    )
    if duplicates:
        raise DuplicateWatchEntry(duplicates=duplicates)

    try:
        with pg_engine.begin() as conn:  # commits or rolls back on exit
            for r in rows:
                conn.execute(UPSERT_WATCHED, {"gamePk": r.gamePk, "watched": r.watched})
    except OperationalError as e:
        raise DataSourceUnavailable() from e
    except ProgrammingError as e:
        raise InternalError("A required table is missing from the database.") from e
    return {"updated": len(rows)}
