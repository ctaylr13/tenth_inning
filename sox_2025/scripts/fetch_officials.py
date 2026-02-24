import requests
import pandas as pd
import duckdb
import time
import traceback
from typing import Dict, Any, Optional, List

DB_PATH = "../../redsox_25.duckdb"
BASE_URL_TEMPLATE = "https://statsapi.mlb.com/api/v1/game/{gamePk}/withMetrics"
TIMEOUT = 60
SLEEP_BETWEEN = 0.15  # throttle


def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def map_officials_list(olist: Optional[List[Dict[str, Any]]]) -> Dict[str, Optional[Any]]:
    out = {
        "home_plate_id": None, "home_plate_name": None,
        "first_base_id": None, "first_base_name": None,
        "second_base_id": None, "second_base_name": None,
        "third_base_id": None, "third_base_name": None,
    }
    for o in olist or []:
        oid = safe_get(o, "official", "id")
        name = safe_get(o, "official", "fullName")
        typ = o.get("officialType")
        if oid is None and name is None:
            continue
        if typ == "Home Plate":
            out["home_plate_id"] = int(oid) if oid is not None else None
            out["home_plate_name"] = name
        elif typ == "First Base":
            out["first_base_id"] = int(oid) if oid is not None else None
            out["first_base_name"] = name
        elif typ == "Second Base":
            out["second_base_id"] = int(oid) if oid is not None else None
            out["second_base_name"] = name
        elif typ == "Third Base":
            out["third_base_id"] = int(oid) if oid is not None else None
            out["third_base_name"] = name
    return out


def extract_officials(payload: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    box = safe_get(payload, "liveData", "boxscore", "officials")
    if box:
        return map_officials_list(box)
    cur = safe_get(payload, "liveData", "currentPlay", "playEvents", default=[])
    for pe in cur:
        if pe.get("officials"):
            return map_officials_list(pe["officials"])
    allp = safe_get(payload, "liveData", "plays", "allPlays", default=[])
    for play in allp:
        for pe in play.get("playEvents", []) or []:
            if pe.get("officials"):
                return map_officials_list(pe["officials"])
    return map_officials_list([])


def ensure_officials_schema(conn: duckdb.DuckDBPyConnection) -> None:
    required = {
        "home_plate_id": "INTEGER",
        "home_plate_name": "VARCHAR",
        "first_base_id": "INTEGER",
        "first_base_name": "VARCHAR",
        "second_base_id": "INTEGER",
        "second_base_name": "VARCHAR",
        "third_base_id": "INTEGER",
        "third_base_name": "VARCHAR",
    }
    tbl_info = conn.execute("PRAGMA table_info('game_officials')").fetchall()
    existing = {r[1] for r in tbl_info}  # column names
    if not existing:
        conn.execute("""
        CREATE TABLE game_officials (
            gamePk BIGINT PRIMARY KEY
        )
        """)
        existing = {"gamePk"}
    for col, ctype in required.items():
        if col not in existing:
            conn.execute(f'ALTER TABLE game_officials ADD COLUMN {col} {ctype}')
    # copy legacy numeric columns if they exist (home_plate, first_base, etc.)
    legacy_to_new = {
        "home_plate": "home_plate_id",
        "first_base": "first_base_id",
        "second_base": "second_base_id",
        "third_base": "third_base_id",
    }
    existing = {r[1] for r in conn.execute("PRAGMA table_info('game_officials')").fetchall()}
    for old, new in legacy_to_new.items():
        if old in existing:
            conn.execute(f'''
            UPDATE game_officials
            SET {new} = COALESCE({new}, {old})
            WHERE {new} IS NULL AND {old} IS NOT NULL
            ''')


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS game_officials (
        gamePk BIGINT PRIMARY KEY
    )
    """)


def get_gamepks(conn: duckdb.DuckDBPyConnection) -> List[int]:
    df = conn.execute('SELECT gamePk FROM "2025_schedule"').fetchdf()
    return df["gamePk"].astype(int).tolist() if not df.empty else []


def fetch_payload(session: requests.Session, gamePk: int) -> Optional[Dict[str, Any]]:
    url = BASE_URL_TEMPLATE.format(gamePk=gamePk)
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Request error for {gamePk}: {e}")
        return None


def upsert_game_officials(conn: duckdb.DuckDBPyConnection, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("No official rows to upsert.")
        return
    df = pd.DataFrame(rows)
    conn.register("tmp_off", df)
    conn.execute("""
    CREATE TEMPORARY TABLE tmp_off_sched AS
    SELECT CAST(gamePk AS BIGINT) AS gamePk,
           home_plate_id, home_plate_name,
           first_base_id, first_base_name,
           second_base_id, second_base_name,
           third_base_id, third_base_name
    FROM tmp_off
    """)
    conn.execute("""
    MERGE INTO game_officials AS target
    USING tmp_off_sched AS src
    ON target.gamePk = src.gamePk
    WHEN MATCHED THEN
      UPDATE SET
        home_plate_id = COALESCE(src.home_plate_id, target.home_plate_id),
        home_plate_name = COALESCE(src.home_plate_name, target.home_plate_name),
        first_base_id = COALESCE(src.first_base_id, target.first_base_id),
        first_base_name = COALESCE(src.first_base_name, target.first_base_name),
        second_base_id = COALESCE(src.second_base_id, target.second_base_id),
        second_base_name = COALESCE(src.second_base_name, target.second_base_name),
        third_base_id = COALESCE(src.third_base_id, target.third_base_id),
        third_base_name = COALESCE(src.third_base_name, target.third_base_name)
    WHEN NOT MATCHED THEN
      INSERT (gamePk, home_plate_id, home_plate_name, first_base_id, first_base_name,
              second_base_id, second_base_name, third_base_id, third_base_name)
      VALUES (src.gamePk, src.home_plate_id, src.home_plate_name, src.first_base_id, src.first_base_name,
              src.second_base_id, src.second_base_name, src.third_base_id, src.third_base_name);
    """)
    conn.unregister("tmp_off")
    print(f"Upserted {len(df)} rows into game_officials.")

def get_existing_gamepks(conn: duckdb.DuckDBPyConnection) -> List[int]:
    """
    Fetch the list of gamePks that already exist in the game_officials table.
    """
    df = conn.execute('SELECT gamePk FROM game_officials').fetchdf()
    return df["gamePk"].astype(int).tolist() if not df.empty else []


def fetch_and_store_all_officials(verbose: bool = True) -> None:
    try:
        conn = duckdb.connect(DB_PATH)
    except Exception:
        print("Failed to open DuckDB:", traceback.format_exc())
        return
    try:
        ensure_table(conn)
        ensure_officials_schema(conn)
        gamepks = get_gamepks(conn)
        existing_gamepks = set(get_existing_gamepks(conn))
        print("Total gamePk count from 2025_schedule:", len(gamepks))
        print("Existing gamePk count in game_officials:", len(existing_gamepks))

        # Remove duplicates from gamepks and filter out existing gamePks
        gamepks_to_process = list(set(gamepks) - existing_gamepks)
        print("GamePks to process (after removing duplicates):", len(gamepks_to_process))

        if not gamepks_to_process:
            conn.close()
            return

        session = requests.Session()
        rows: List[Dict[str, Any]] = []
        for i, gp in enumerate(gamepks_to_process, start=1):
            if verbose and i % 50 == 0:
                print(f"Processing {i}/{len(gamepks_to_process)} (gamePk={gp})")
            payload = fetch_payload(session, gp)
            if payload is None:
                continue
            offs = extract_officials(payload)
            if any(offs[v] is not None for v in offs):
                row = {"gamePk": int(gp)}
                row.update(offs)
                rows.append(row)
                if verbose:
                    print(f"  fetched officials for {gp}: {offs}")
            else:
                if verbose:
                    print(f"  no officials found for {gp}")
            time.sleep(SLEEP_BETWEEN)

        upsert_game_officials(conn, rows)
    except Exception:
        print("Unexpected error:\n", traceback.format_exc())
    finally:
        conn.close()


fetch_and_store_all_officials()