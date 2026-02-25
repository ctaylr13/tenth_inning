from prefect import flow, task, get_run_logger
import requests
import duckdb
import time
from prefect.task_runners import ConcurrentTaskRunner

DB_PATH = "../../redsox_25.duckdb"

# ============================================================
# GAME SELECTION
# ============================================================

@task
def get_new_games_game_pks():
    with duckdb.connect(DB_PATH) as con:

        all_games = con.execute("""
            SELECT DISTINCT gamePk
            FROM main."2025_schedule"
        """).fetchall()

        # IMPORTANT: Check defensive credits table
        ingested = con.execute("""
            SELECT DISTINCT game_pk
            FROM runner_defensive_credits
        """).fetchall()

    all_game_pks = {row[0] for row in all_games}
    ingested_pks = {row[0] for row in ingested}

    new_games = sorted(all_game_pks - ingested_pks)

    print(f"{len(new_games)} games missing defensive credits.")

    return new_games


# ============================================================
# ROW BUILDERS (PURE)
# ============================================================

@task
def build_runner_credit_rows(plays, game_pk):
    rows = []

    for play in plays:
        pa_id = play["about"]["atBatIndex"]
        event_type = play["result"]["eventType"]

        for runner in play.get("runners", []):
            runner_id = runner.get("details", {}).get("runner", {}).get("id")

            for credit in runner.get("credits", []):
                rows.append((
                    game_pk,
                    pa_id,
                    runner_id,
                    event_type,
                    credit.get("credit"),
                    credit.get("player", {}).get("id"),
                    credit.get("position", {}).get("code"),
                ))

    return rows


# ============================================================
# DB WRITER
# ============================================================

@task
def write_runner_credits_to_db(game_pk, runner_credit_rows):

    with duckdb.connect(DB_PATH) as con:
        con.execute("BEGIN")

        con.execute("""
        CREATE TABLE IF NOT EXISTS runner_defensive_credits (
            game_pk        INTEGER NOT NULL,
            pa_id          INTEGER NOT NULL,
            runner_id      INTEGER,
            event_type     VARCHAR,
            credit_type    VARCHAR,
            player_id      INTEGER,
            position_code  VARCHAR,
            PRIMARY KEY (game_pk, pa_id, runner_id, credit_type, player_id)
        );
        """)

        con.execute(
            "DELETE FROM runner_defensive_credits WHERE game_pk = ?",
            (game_pk,)
        )

        con.executemany("""
            INSERT INTO runner_defensive_credits
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, runner_credit_rows)

        con.execute("COMMIT")


# ============================================================
# SINGLE GAME INGEST
# ============================================================

@task(name="ingest_game", task_run_name="game-{game_pk}")
def ingest_game(game_pk: int):

    logger = get_run_logger()
    start_time = time.time()

    logger.info(f"Starting ingest for game {game_pk}")

    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/withMetrics"
    data = requests.get(url, timeout=60).json()

    plays = data["liveData"]["plays"]["allPlays"]

    runner_credit_rows = build_runner_credit_rows(plays, game_pk)

    write_runner_credits_to_db(
        game_pk,
        runner_credit_rows
    )

    duration = round(time.time() - start_time, 2)
    logger.info(f"Finished game {game_pk} in {duration} seconds")


# ============================================================
# SEASON FLOW (CONCURRENT)
# ============================================================

@flow(
    name="runner_defensive_credit_ingestion",
    flow_run_name="2025_runner_credit_backfill",
    task_runner=ConcurrentTaskRunner(max_workers=5)
)
def ingest_season():

    logger = get_run_logger()

    game_pks = get_new_games_game_pks()

    # 👇 TEST CAP (first 10 only)
    # game_pks = game_pks[:10]

    logger.info(f"Processing {len(game_pks)} games (test mode)")

    futures = []

    for game_pk in game_pks:
        futures.append(ingest_game.submit(game_pk))

    for f in futures:
        f.result()

    logger.info("Season ingest complete.")


if __name__ == "__main__":
    ingest_season()