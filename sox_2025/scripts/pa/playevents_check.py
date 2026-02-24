import requests
import json

GAME_PK = 778553
LIMIT = 3  # number of plate appearances to inspect

url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]

home_team_id = data["gameData"]["teams"]["home"]["id"]
away_team_id = data["gameData"]["teams"]["away"]["id"]

print("\n=== PITCH EVENT EXTRACTION TEST WITH CONTEXT ===\n")

for play in all_plays[:LIMIT]:

    about = play["about"]
    matchup = play["matchup"]

    pa_id = about["atBatIndex"]
    half = about["halfInning"]

    team_id = away_team_id if half == "top" else home_team_id
    batter_id = matchup["batter"]["id"]
    pitcher_id = matchup["pitcher"]["id"]

    play_events = play.get("playEvents", [])

    print(f"\nPA ID: {pa_id}")

    for event in play_events:

        if not event.get("isPitch"):
            continue

        details = event.get("details", {})
        count = event.get("count", {})
        pre_count = event.get("preCount", {})
        pitch_data = event.get("pitchData", {})
        hit_data = event.get("hitData", {})

        cleaned_event = {
            # Context
            "game_pk": GAME_PK,
            "team_id": team_id,
            "pa_id": pa_id,
            "batter_id": batter_id,
            "pitcher_id": pitcher_id,
            "pitch_number": event.get("pitchNumber"),

            # Details
            "description": details.get("description"),
            "code": details.get("code"),
            "isInPlay": details.get("isInPlay"),
            "isStrike": details.get("isStrike"),
            "isBall": details.get("isBall"),
            "pitch_type_code": details.get("type", {}).get("code"),
            "pitch_type_desc": details.get("type", {}).get("description"),
            "isOut": details.get("isOut"),

            # Count
            "balls": count.get("balls"),
            "strikes": count.get("strikes"),
            "outs": count.get("outs"),
            "pre_balls": pre_count.get("balls"),
            "pre_strikes": pre_count.get("strikes"),
            "pre_outs": pre_count.get("outs"),

            # Pitch Data
            "startSpeed": pitch_data.get("startSpeed"),
            "endSpeed": pitch_data.get("endSpeed"),
            "zone": pitch_data.get("zone"),
            "plateTime": pitch_data.get("plateTime"),
            "extension": pitch_data.get("extension"),
            "pX": pitch_data.get("coordinates", {}).get("pX"),
            "pZ": pitch_data.get("coordinates", {}).get("pZ"),
            "spinRate": pitch_data.get("breaks", {}).get("spinRate"),

            # Hit Data
            "batSpeed": hit_data.get("batSpeed"),
            "isSwordSwing": hit_data.get("isSwordSwing"),
        }

        print(json.dumps(cleaned_event, indent=2))

    print("-" * 80)