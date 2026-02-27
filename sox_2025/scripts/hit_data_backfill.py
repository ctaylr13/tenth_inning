from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
import requests
import duckdb

DB_PATH = "../../redsox_25.duckdb"

# ============================================================
# Ensure Columns Exist
# ============================================================

@task
def ensure_hit_columns_exist():
    with duckdb.connect(DB_PATH) as con:

        columns = [
            ("launch_speed", "DOUBLE"),
            ("launch_angle", "DOUBLE"),
            ("total_distance", "DOUBLE"),
            ("trajectory", "VARCHAR"),
            ("hardness", "VARCHAR"),
            ("hit_location", "VARCHAR"),
            ("hit_coord_x", "DOUBLE"),
            ("hit_coord_y", "DOUBLE"),
            ("hit_probability", "DOUBLE"),
        ]

        existing_cols = {
            row[0]
            for row in con.execute(
                "PRAGMA table_info('pa_plate_events')"
            ).fetchall()
        }

        for col_name, col_type in columns:
            if col_name not in existing_cols:
                print(f"Adding column {col_name}")
                con.execute(
                    f"ALTER TABLE pa_plate_events ADD COLUMN {col_name} {col_type}"
                )

    print("Column check complete.")


# ============================================================
# Get All Games
# ============================================================

@task
def get_all_games():
    with duckdb.connect(DB_PATH) as con:
        rows = con.execute("""
            SELECT DISTINCT gamePk
            FROM main."2025_game_info"
            ORDER BY gamePk
        """).fetchall()

    game_pks = [r[0] for r in rows]
    print(f"Found {len(game_pks)} games to process.")
    return game_pks


# ============================================================
# Backfill One Game
# ============================================================

@task
def backfill_game_hitdata(game_pk: int):

    print(f"Processing game {game_pk}")

    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/withMetrics"
    data = requests.get(url, timeout=60).json()
    plays = data["liveData"]["plays"]["allPlays"]

    with duckdb.connect(DB_PATH) as con:

        for play in plays:
            pa_id = play["about"]["atBatIndex"]

            for event in play.get("playEvents", []):

                if not event.get("isPitch"):
                    continue

                pitch_number = event.get("pitchNumber")
                hit_data = event.get("hitData", {})

                if not hit_data:
                    continue

                con.execute("""
                    UPDATE pa_plate_events
                    SET
                        launch_speed = ?,
                        launch_angle = ?,
                        total_distance = ?,
                        trajectory = ?,
                        hardness = ?,
                        hit_location = ?,
                        hit_coord_x = ?,
                        hit_coord_y = ?,
                        hit_probability = ?
                    WHERE game_pk = ?
                      AND pa_id = ?
                      AND pitch_number = ?
                """, (
                    hit_data.get("launchSpeed"),
                    hit_data.get("launchAngle"),
                    hit_data.get("totalDistance"),
                    hit_data.get("trajectory"),
                    hit_data.get("hardness"),
                    hit_data.get("location"),
                    hit_data.get("coordinates", {}).get("coordX"),
                    hit_data.get("coordinates", {}).get("coordY"),
                    hit_data.get("hitProbability"),
                    game_pk,
                    pa_id,
                    pitch_number
                ))

    print(f"Finished game {game_pk}")


# ============================================================
# Flow
# ============================================================

@flow(
    name="hitdata_backfill",
    task_runner=ConcurrentTaskRunner(max_workers=5)
)
def backfill_hitdata_season():

    ensure_hit_columns_exist()

    game_pks = get_all_games()

    futures = []
    for game_pk in game_pks:
        futures.append(backfill_game_hitdata.submit(game_pk))

    for f in futures:
        f.result()

    print("HitData backfill complete.")


if __name__ == "__main__":
    backfill_hitdata_season()