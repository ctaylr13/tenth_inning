#!/usr/bin/env python3
import time
import requests
import duckdb
import pandas as pd
from typing import Dict, Any, Set, List
from tqdm import tqdm

DB_PATH = "../../redsox_25.duckdb"  # adjust
BOX_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"
TIMEOUT = 30
SLEEP = 0.08
USER_AGENT = "tenth-inning-box/1.0"

TABLES = {
    "batting": "batting_game_stats",
    "pitching": "pitching_game_stats",
    "fielding": "fielding_game_stats",
}


def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def ensure_table(conn: duckdb.DuckDBPyConnection, table: str):
    conn.execute(
        f'''
        CREATE TABLE IF NOT EXISTS "{table}" (
          gamePk BIGINT,
          side VARCHAR,
          teamId INTEGER
        )
        '''
    )


def existing_columns(conn: duckdb.DuckDBPyConnection, table: str) -> Set[str]:
    return set(r[0] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall())


def add_col_if_missing(conn: duckdb.DuckDBPyConnection, table: str, col: str):
    cols = existing_columns(conn, table)
    if col in cols:
        return
    try:
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR')
    except Exception:
        # ignore race/duplicate errors
        pass


def upsert_row(conn: duckdb.DuckDBPyConnection, table: str, row: Dict[str, Any]):
    df = pd.DataFrame([row])
    conn.register("tmp_up", df)
    # create temp table from df
    cols_payload = [c for c in row.keys() if c not in ("gamePk", "side", "teamId")]
    select_cols = ["CAST(gamePk AS BIGINT) AS gamePk", "side", "CAST(teamId AS BIGINT) AS teamId"] + [
        f'{("NULL" if c is None else f""""{c}""" )}::VARCHAR AS "{c}"' for c in cols_payload
    ]
    # simpler: build temp table selecting all columns from tmp_up with casts
    conn.execute(
        """
        CREATE TEMPORARY TABLE tmp_row AS
        SELECT CAST(gamePk AS BIGINT) AS gamePk,
               side,
               CAST(teamId AS BIGINT) AS teamId,
               """ + ", ".join([f'"{c}"::VARCHAR AS "{c}"' for c in cols_payload]) + """
        FROM tmp_up
        """
    )
    # update existing
    set_clause = ",\n    ".join([f'"{c}" = COALESCE(u."{c}", t."{c}")' for c in cols_payload])
    conn.execute(
        f'''
        UPDATE "{table}" AS t
        SET
          teamId = COALESCE(u.teamId, t.teamId)
          {", " if set_clause else ""}
          {set_clause if set_clause else ""}
        FROM tmp_row u
        WHERE t.gamePk = u.gamePk AND t.side = u.side
        '''
    )
    # insert missing
    cols_all = ["gamePk", "side", "teamId"] + cols_payload
    conn.execute(
        f'''
        INSERT INTO "{table}" ({", ".join('"' + c + '"' for c in cols_all)})
        SELECT {", ".join(f'u."{c}"' for c in cols_all)}
        FROM tmp_row u
        LEFT JOIN "{table}" t ON t.gamePk = u.gamePk AND t.side = u.side
        WHERE t.gamePk IS NULL
        '''
    )
    conn.unregister("tmp_up")
    conn.execute("DROP TABLE IF EXISTS tmp_row")


def flatten_stats(obj: Dict[str, Any]) -> Dict[str, str]:
    return {k: (str(v) if v is not None else None) for k, v in obj.items()}


def main():
    conn = duckdb.connect(DB_PATH)
    # get gamePks from schedule
    existing = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()
    game_pks = existing["gamePk"].astype(int).tolist()
    print("Games to process:", len(game_pks))

    # ensure tables exist
    for t in TABLES.values():
        ensure_table(conn, t)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for pk in tqdm(game_pks, desc="games"):
        url = BOX_URL.format(pk=pk)
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            print(f"[{pk}] fetch error: {e}")
            time.sleep(SLEEP)
            continue

        # assume teamStats located at payload["teamStats"] or payload["teams"][side]["teamStats"]
        team_stats_block = payload.get("teamStats") or {}
        if not team_stats_block:
            teams_block = payload.get("teams", {})
            for side in ("home", "away"):
                ts = teams_block.get(side, {}).get("teamStats")
                if ts:
                    team_stats_block[side] = ts

        if not team_stats_block:
            print(f"[{pk}] no teamStats found; skipping")
            time.sleep(SLEEP)
            continue

        for side in ("home", "away"):
            stats = team_stats_block.get(side)
            if not isinstance(stats, dict):
                continue
            # find team id
            team_id = safe_get(payload, "teams", side, "team", "id") or safe_get(payload, "teams", side, "id")
            team_id = int(team_id) if team_id is not None else None

            for cat, table in TABLES.items():
                cat_stats = stats.get(cat)
                if not isinstance(cat_stats, dict):
                    continue
                # ensure columns exist
                for col in cat_stats.keys():
                    add_col_if_missing(conn, table, col)
                # build row: includes teamId
                row = {"gamePk": pk, "side": side, "teamId": team_id}
                for k, v in cat_stats.items():
                    row[k] = str(v) if v is not None else None
                upsert_row(conn, table, row)

        print(f"[{pk}] processed")
        time.sleep(SLEEP)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
