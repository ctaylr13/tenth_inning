import requests
import json

GAME_PK = 778553

url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

plays = data["liveData"]["plays"]["allPlays"]


# ---------------------------------------------------
# Build Plate Appearance Rows
# ---------------------------------------------------
plate_appearances = []

for play in plays:
    about = play["about"]
    matchup = play["matchup"]
    result = play["result"]

    outs_after = play["count"]["outs"]
    event_type = result["eventType"]

    pa_row = {
        "game_pk": GAME_PK,
        "pa_id": about["atBatIndex"],
        "inning": about["inning"],
        "half": about["halfInning"],
        "batter_id": matchup["batter"]["id"],
        "pitcher_id": matchup["pitcher"]["id"],
        "event_type": event_type,
        "event_desc": result.get("description"),
    }

    plate_appearances.append(pa_row)

# ---------------------------------------------------
# Preview
# ---------------------------------------------------
print(json.dumps(plate_appearances[0:], indent=2))
print("\nTotal Plate Appearances:", len(plate_appearances))