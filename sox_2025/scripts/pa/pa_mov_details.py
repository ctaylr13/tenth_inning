import requests
import json

GAME_PK = 778553
LIMIT = 10

url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]

print("\n=== CLEANED RUNNER MOVEMENT (First 10 PAs) ===\n")

for play in all_plays[:LIMIT]:

    pa_id = play["about"]["atBatIndex"]
    runners = play.get("runners", [])

    if not runners:
        continue

    print(f"\nPA ID: {pa_id}")

    for runner in runners:

        movement = runner.get("movement", {})
        details = runner.get("details", {})

        cleaned_details = {
            "event": details.get("event"),
            "eventType": details.get("eventType"),
            "movementReason": details.get("movementReason"),
            "runner_id": details.get("runner", {}).get("id"),
            "responsiblePitcher": details.get("responsiblePitcher"),
            "isScoringEvent": details.get("isScoringEvent"),
            "rbi": details.get("rbi"),
            "earned": details.get("earned"),
            "teamUnearned": details.get("teamUnearned"),
            "playIndex": details.get("playIndex")
        }

        cleaned_runner = {
            "movement": movement,
            "details": cleaned_details
        }

        print(json.dumps(cleaned_runner, indent=2))

    print("-" * 70)