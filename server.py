import asyncio
import json
import logging
import os
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import duckdb
import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi import Path as FastPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from error_handlers import get_request_id, install_error_handling
from errors import (
    DataSourceUnavailable,
    DuplicateWatchEntry,
    InternalError,
    ResourceNotFound,
    ValidationFailed,
)
from live import TERMINAL_TYPES, Broadcaster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DB_PATH = "redsox_25.duckdb"  # optional: make absolute
SCHEDULE_TABLE = 'main."2025_schedule"'
WATCH_TABLE = 'main."watch_history"'
GAME_INFO_TABLE = 'main."2025_game_info"'
LINESCORE_TABLE = 'main."line_score_innings"'


class WatchRow(BaseModel):
    gamePk: int
    watched: bool


app = FastAPI()
install_error_handling(app)

# The Vite proxy makes dev calls same-origin, so a wrong value here is never
# exercised until deploy. From the environment, so it can be right there.
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


def _safe_rollback(conn) -> None:
    """Roll back without ever masking the exception that got us here."""
    try:
        conn.execute("ROLLBACK")
    except duckdb.Error:
        logger.warning("ROLLBACK failed", exc_info=True)


def get_conn():
    # duckdb.connect() creates a missing file instead of raising -- without
    # this, a fresh clone reports "table missing" instead of the real problem.
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
    where, params = ["1 = 1"], []
    if month is not None:
        where.append("MONTH(s.officialDate) = ?")
        params.append(month)
    if result is not None:
        where.append("s.sox_is_winner = ?")
        params.append(result is GameResult.win)
    if watched is not None:
        where.append("COALESCE(w.watched, FALSE) = ?")
        params.append(watched)
    clause = " AND ".join(where)

    joined = f"""
        FROM {SCHEDULE_TABLE} s
        LEFT JOIN (
            SELECT gamePk, MAX(watched::INT)::BOOLEAN AS watched
            FROM {WATCH_TABLE} GROUP BY gamePk
        ) w USING (gamePk)
        WHERE {clause}
    """

    total = _read(f"SELECT COUNT(*) AS n {joined}", params)[0]["n"]
    items = _read(
        f"""
        SELECT s.gamePk,
               s.gameDate::VARCHAR AS gameDate,
               s.officialDate::VARCHAR AS officialDate,
               s.doubleheader,
               s.home_score, s.away_score, s.sox_is_winner,
               COALESCE(w.watched, FALSE) AS watched
        {joined}
        ORDER BY s.gameDate
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    # A filter that matches nothing is an empty page, not an error.
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


@app.get("/api/games/{gamePk}")
def get_game(gamePk: Annotated[int, FastPath(gt=0)]) -> dict[str, Any]:
    """One game. A gamePk that parses but doesn't exist is a 404, not a 422."""
    rows = _read(
        f"""
        SELECT g.*, s.gameDate::VARCHAR AS gameDate, s.doubleheader,
               COALESCE(w.watched, FALSE) AS watched
        FROM {GAME_INFO_TABLE} g
        JOIN {SCHEDULE_TABLE} s USING (gamePk)
        LEFT JOIN (
            SELECT gamePk, MAX(watched::INT)::BOOLEAN AS watched
            FROM {WATCH_TABLE} GROUP BY gamePk
        ) w USING (gamePk)
        WHERE g.gamePk = ?
        """,
        [gamePk],
    )
    if not rows:
        raise ResourceNotFound(f"No game with gamePk {gamePk}.", gamePk=gamePk)
    return rows[0]


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


@app.get("/api/schedule")
def get_schedule() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        # LEFT JOIN watched where the table exists, else default FALSE.
        tables = [r[0].lower() for r in conn.execute("SHOW TABLES").fetchall()]
        has_watch = "watch_history" in tables

        if has_watch:
            sql = f"""
            SELECT s.gamePk,
                s.gameDate::VARCHAR AS gameDate,
                s.officialDate::VARCHAR AS officialDate,
                s.doubleheader,
                COALESCE(w.watched, FALSE) AS watched
            FROM {SCHEDULE_TABLE} s
            LEFT JOIN (
                SELECT gamePk, MAX(watched::INT)::BOOLEAN AS watched
                FROM {WATCH_TABLE}
                GROUP BY gamePk
            ) w USING (gamePk)
            ORDER BY s.gameDate
            """
        else:
            sql = f"""
            SELECT s.gamePk,
                   s.gameDate::VARCHAR AS gameDate,
                   s.officialDate::VARCHAR AS officialDate,
                   s.doubleheader,
                   FALSE AS watched
            FROM {SCHEDULE_TABLE} s
            ORDER BY s.gameDate
            """
        df = conn.execute(sql).fetchdf()
        # Zero games is an empty state: 200 [], never 204 -- [] is a body.
        return df.where(pd.notnull(df), None).to_dict(orient="records")
    except duckdb.CatalogException as e:
        # Our schema is broken, not their request.
        raise InternalError("A required table is missing from the database.") from e
    except duckdb.IOException as e:
        raise DataSourceUnavailable() from e
    finally:
        conn.close()


@app.put("/api/watchhistory")
def update_watchhistory(rows: list[WatchRow]):
    if not rows:
        # 400 not 422: the body parsed, it just carries nothing to do.
        raise ValidationFailed("No rows provided.", status_code=400)

    # Ambiguous when duplicates disagree, and watch_history has no unique key.
    duplicates = sorted(
        pk for pk, n in Counter(r.gamePk for r in rows).items() if n > 1
    )
    if duplicates:
        raise DuplicateWatchEntry(duplicates=duplicates)

    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS "watch_history" (
                gamePk BIGINT,
                watched BOOLEAN DEFAULT FALSE
            )
        """)

        conn.execute("BEGIN TRANSACTION")
        df_tmp = pd.DataFrame([r.model_dump() for r in rows])
        conn.register("tmp_rows", df_tmp)

        conn.execute("""
            CREATE TEMPORARY TABLE tmp_watch AS
            SELECT CAST(gamePk AS BIGINT) AS gamePk, watched::BOOLEAN AS watched FROM tmp_rows
        """)

        conn.execute("""
            UPDATE "watch_history" AS w
            SET watched = t.watched
            FROM tmp_watch t
            WHERE w.gamePk = t.gamePk
        """)

        conn.execute("""
            INSERT INTO "watch_history"(gamePk, watched)
            SELECT t.gamePk, t.watched
            FROM tmp_watch t
            LEFT JOIN "watch_history" w ON t.gamePk = w.gamePk
            WHERE w.gamePk IS NULL
        """)

        conn.execute("COMMIT")
        conn.unregister("tmp_rows")
        return {"updated": len(rows)}
    except duckdb.IOException as e:
        _safe_rollback(conn)
        raise DataSourceUnavailable() from e
    except duckdb.CatalogException as e:
        _safe_rollback(conn)
        raise InternalError("A required table is missing from the database.") from e
    except Exception:
        # Re-raise unclassified -- handle_unexpected logs it and returns a 500.
        _safe_rollback(conn)
        raise
    finally:
        conn.close()
