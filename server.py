from fastapi import FastAPI, HTTPException
import duckdb
import pandas as pd
from typing import List, Dict, Any
from pathlib import Path
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


DB_PATH = "redsox_25.duckdb"  # optional: make absolute
SCHEDULE_TABLE = 'main."2025_schedule"'
WATCH_TABLE = 'main."watch_history"'  # adjust if you use a different name

class WatchRow(BaseModel):
    gamePk: int
    watched: bool

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your frontend origin (use "*" only for dev if needed)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

def get_conn():
    return duckdb.connect(DB_PATH)

@app.get("/api/schedule")
def get_schedule() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        # If watch_history exists, include watched via LEFT JOIN; otherwise default watched = false
        tables = [r[0].lower() for r in conn.execute("SHOW TABLES").fetchall()]
        has_watch = "watch_history" in tables

        if has_watch:
            sql = f'''
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
            '''
        else:
            sql = f'''
            SELECT s.gamePk,
                   s.gameDate::VARCHAR AS gameDate,
                   s.officialDate::VARCHAR AS officialDate,
                   s.doubleheader,
                   FALSE AS watched
            FROM {SCHEDULE_TABLE} s
            ORDER BY s.gameDate
            '''
        df = conn.execute(sql).fetchdf()
        return df.where(pd.notnull(df), None).to_dict(orient="records")
    finally:
        conn.close()


class WatchRow(BaseModel):
    gamePk: int
    watched: bool

@app.put("/api/watchhistory")
def update_watchhistory(rows: List[WatchRow]):
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    conn = get_conn()
    try:
        # ensure watch_history table exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS "watch_history" (
                gamePk BIGINT,
                watched BOOLEAN DEFAULT FALSE
            )
        ''')

        conn.execute("BEGIN TRANSACTION")
        # register payload as a pandas DataFrame
        df_tmp = pd.DataFrame([r.dict() for r in rows])
        conn.register("tmp_rows", df_tmp)

        conn.execute("""
            CREATE TEMPORARY TABLE tmp_watch AS
            SELECT CAST(gamePk AS BIGINT) AS gamePk, watched::BOOLEAN AS watched FROM tmp_rows
        """)

        # update existing watch rows
        conn.execute('''
            UPDATE "watch_history" AS w
            SET watched = t.watched
            FROM tmp_watch t
            WHERE w.gamePk = t.gamePk
        ''')

        # insert missing rows
        conn.execute('''
            INSERT INTO "watch_history"(gamePk, watched)
            SELECT t.gamePk, t.watched
            FROM tmp_watch t
            LEFT JOIN "watch_history" w ON t.gamePk = w.gamePk
            WHERE w.gamePk IS NULL
        ''')

        conn.execute("COMMIT")
        conn.unregister("tmp_rows")
        return {"updated": len(rows)}
    except Exception as e:
        conn.execute("ROLLBACK")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



