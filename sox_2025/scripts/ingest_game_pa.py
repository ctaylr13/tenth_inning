from prefect import flow, task
import requests
import duckdb

DB_PATH = "../../redsox_25.duckdb"

@task
def get_new_games_game_pks():
    with duckdb.connect(DB_PATH) as con:

        # All scheduled games
        all_games = con.execute("""
            SELECT DISTINCT gamePk
            FROM main."2025_schedule"
        """).fetchall()

        # Already ingested games
        ingested = con.execute("""
            SELECT DISTINCT game_pk
            FROM main."2025_game_plate_appearance"
        """).fetchall()

    all_game_pks = {row[0] for row in all_games}
    ingested_pks = {row[0] for row in ingested}

    new_games = sorted(all_game_pks - ingested_pks)

    print(f"{len(new_games)} games remaining to ingest.")

    return new_games


# ============================================================
# ROW BUILDERS (PURE — NO DB SIDE EFFECTS)
# ============================================================

@task
def build_pa_rows(plays, game_pk, home_team_id, away_team_id):
    rows = []

    for play in plays:
        about = play["about"]
        result = play["result"]
        count = play["count"]
        matchup = play["matchup"]

        pa_id = about["atBatIndex"]
        half = about["halfInning"]
        team_id = away_team_id if half == "top" else home_team_id

        credits = play.get("credits", [])
        b_pa = p_pa = b_ab = p_ab = None

        for credit in credits:
            credit_type = credit.get("credit")
            player_id = credit.get("player", {}).get("id")

            if credit_type == "b_pa":
                b_pa = player_id
            elif credit_type == "p_pa":
                p_pa = player_id
            elif credit_type == "b_ab":
                b_ab = player_id
            elif credit_type == "p_ab":
                p_ab = player_id

        rows.append((
            game_pk,
            pa_id,
            team_id,
            about.get("halfInning"),
            about.get("isTopInning"),
            about.get("inning"),
            about.get("isScoringPlay"),
            about.get("hasOut"),
            matchup.get("batter", {}).get("id"),
            matchup.get("pitcher", {}).get("id"),
            result.get("type"),
            result.get("event"),
            result.get("eventType"),
            result.get("description"),
            result.get("rbi"),
            result.get("awayScore"),
            result.get("homeScore"),
            result.get("isOut"),
            count.get("balls"),
            count.get("strikes"),
            count.get("outs"),
            play.get("pitchIndex"),
            play.get("actionIndex"),
            play.get("runnerIndex"),
            b_pa,
            p_pa,
            b_ab,
            p_ab,
        ))

    return rows


@task
def build_pitch_rows(plays, game_pk, home_team_id, away_team_id):
    rows = []

    for play in plays:
        about = play["about"]
        matchup = play["matchup"]

        pa_id = about["atBatIndex"]
        half = about["halfInning"]
        team_id = away_team_id if half == "top" else home_team_id

        for event in play.get("playEvents", []):
            if not event.get("isPitch"):
                continue

            details = event.get("details", {})
            count = event.get("count", {})
            pre_count = event.get("preCount", {})
            pitch_data = event.get("pitchData", {})
            hit_data = event.get("hitData", {})

            rows.append((
                game_pk,
                team_id,
                pa_id,
                event.get("pitchNumber"),
                matchup["batter"]["id"],
                matchup["pitcher"]["id"],
                details.get("description"),
                details.get("code"),
                details.get("isInPlay"),
                details.get("isStrike"),
                details.get("isBall"),
                details.get("type", {}).get("code"),
                details.get("type", {}).get("description"),
                details.get("isOut"),
                count.get("balls"),
                count.get("strikes"),
                count.get("outs"),
                pre_count.get("balls"),
                pre_count.get("strikes"),
                pre_count.get("outs"),
                pitch_data.get("startSpeed"),
                pitch_data.get("endSpeed"),
                pitch_data.get("zone"),
                pitch_data.get("plateTime"),
                pitch_data.get("extension"),
                pitch_data.get("coordinates", {}).get("pX"),
                pitch_data.get("coordinates", {}).get("pZ"),
                pitch_data.get("breaks", {}).get("spinRate"),
                hit_data.get("batSpeed"),
                hit_data.get("isSwordSwing"),
            ))

    return rows


@task
def build_runner_rows(plays, game_pk, home_team_id, away_team_id):
    rows = []

    for play in plays:
        about = play["about"]
        pa_id = about["atBatIndex"]
        half = about["halfInning"]
        team_id = away_team_id if half == "top" else home_team_id

        for runner in play.get("runners", []):
            movement = runner.get("movement", {})
            details = runner.get("details", {})

            responsible_pitcher_obj = details.get("responsiblePitcher")
            responsible_pitcher = (
                responsible_pitcher_obj.get("id")
                if responsible_pitcher_obj else None
            )

            rows.append((
                game_pk,
                pa_id,
                team_id,
                details.get("runner", {}).get("id"),
                movement.get("originBase"),
                movement.get("start"),
                movement.get("end"),
                movement.get("outBase"),
                movement.get("isOut"),
                details.get("event"),
                details.get("eventType"),
                details.get("movementReason"),
                responsible_pitcher,
                details.get("isScoringEvent"),
                details.get("rbi"),
                details.get("earned"),
                details.get("teamUnearned"),
                details.get("playIndex"),
            ))

    return rows


@task
def build_pitch_call_rows(plays, game_pk):
    rows = []

    for play in plays:
        pa_id = play["about"]["atBatIndex"]

        for ev in play.get("playEvents", []):
            if not ev.get("isPitch"):
                continue

            pitch_number = ev.get("pitchNumber")
            if pitch_number is None:
                continue

            pitch_call = ev.get("details", {}).get("call", {}).get("code")

            rows.append((
                game_pk,
                pa_id,
                pitch_number,
                pitch_call
            ))

    return rows


# ============================================================
# SINGLE DB WRITER
# ============================================================

@task
def write_game_to_db(game_pk, pa_rows, pitch_rows, runner_rows, pitch_call_rows):

    with duckdb.connect(DB_PATH) as con:
        con.execute("BEGIN")

        # Create pitches table if needed
        con.execute("""
        CREATE TABLE IF NOT EXISTS pitches (
            game_pk      INTEGER NOT NULL,
            pa_id        INTEGER NOT NULL,
            pitch_number INTEGER NOT NULL,
            pitch_call   VARCHAR NOT NULL,
            PRIMARY KEY (game_pk, pa_id, pitch_number)
        );
        """)

        # Safe re-run deletes
        con.execute("DELETE FROM pa_plate_events WHERE game_pk = ?", (game_pk,))
        con.execute("DELETE FROM main.\"2025_game_plate_appearance\" WHERE game_pk = ?", (game_pk,))
        con.execute("DELETE FROM main.\"2025_plate_appearance_movement_details\" WHERE game_pk = ?", (game_pk,))
        con.execute("DELETE FROM pitches WHERE game_pk = ?", (game_pk,))

        # Insert main tables
        con.executemany("""
            INSERT INTO main."2025_game_plate_appearance"
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, pa_rows)

        con.executemany("""
            INSERT INTO pa_plate_events
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, pitch_rows)

        con.executemany("""
            INSERT INTO main."2025_plate_appearance_movement_details"
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, runner_rows)

        con.executemany("""
            INSERT OR IGNORE INTO pitches
            VALUES (?, ?, ?, ?)
        """, pitch_call_rows)

        con.execute("COMMIT")

    print(f"Game {game_pk} written successfully.")


# ============================================================
# FLOW
# ============================================================

@flow(name="game_plate_appearance_ingestion", flow_run_name="game-{game_pk}")
def ingest_game(game_pk: int):

    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/withMetrics"
    data = requests.get(url, timeout=60).json()

    plays = data["liveData"]["plays"]["allPlays"]
    home_team_id = data["gameData"]["teams"]["home"]["id"]
    away_team_id = data["gameData"]["teams"]["away"]["id"]

    pa_rows = build_pa_rows(plays, game_pk, home_team_id, away_team_id)
    pitch_rows = build_pitch_rows(plays, game_pk, home_team_id, away_team_id)
    runner_rows = build_runner_rows(plays, game_pk, home_team_id, away_team_id)
    pitch_call_rows = build_pitch_call_rows(plays, game_pk)

    write_game_to_db(
        game_pk,
        pa_rows,
        pitch_rows,
        runner_rows,
        pitch_call_rows
    )


if __name__ == "__main__":
    ingest_game(778550)