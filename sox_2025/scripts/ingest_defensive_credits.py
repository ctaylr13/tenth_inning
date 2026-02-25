import requests
import duckdb

DB_PATH = "../../redsox_25.duckdb"
GAME_PK = 778550  # change to test game


def ingest_runner_defensive_credits(game_pk):

    print(f"Fetching game {game_pk}...")

    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/withMetrics"
    data = requests.get(url, timeout=60).json()

    plays = data["liveData"]["plays"]["allPlays"]

    rows = []

    for play in plays:

        pa_id = play["about"]["atBatIndex"]
        event_type = play["result"]["eventType"]

        runners = play.get("runners", [])

        for runner in runners:

            runner_id = runner.get("details", {}).get("runner", {}).get("id")

            for credit in runner.get("credits", []):

                credit_type = credit.get("credit")

                player_id = credit.get("player", {}).get("id")

                position_code = credit.get("position", {}).get("code")

                rows.append((
                    game_pk,
                    pa_id,
                    runner_id,
                    event_type,
                    credit_type,
                    player_id,
                    position_code
                ))

    print(f"Extracted {len(rows)} defensive credit rows.")

    with duckdb.connect(DB_PATH) as con:

        # Create table if needed
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

        # Safe re-run
        con.execute("""
            DELETE FROM runner_defensive_credits
            WHERE game_pk = ?
        """, (game_pk,))

        con.executemany("""
            INSERT INTO runner_defensive_credits
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)

    print(f"Game {game_pk} defensive credits written successfully.")


if __name__ == "__main__":
    ingest_runner_defensive_credits(GAME_PK)