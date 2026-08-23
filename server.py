import logging
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from error_handlers import install_error_handling
from errors import (
    DataSourceUnavailable,
    DuplicateWatchEntry,
    InternalError,
    ValidationFailed,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DB_PATH = "redsox_25.duckdb"  # optional: make absolute
SCHEDULE_TABLE = 'main."2025_schedule"'
WATCH_TABLE = 'main."watch_history"'


class WatchRow(BaseModel):
    gamePk: int
    watched: bool


app = FastAPI()
install_error_handling(app)

app.add_middleware(
    CORSMiddleware,
    # Your frontend origin. Use "*" only for dev, if you need it.
    allow_origins=["http://localhost:5173"],
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
