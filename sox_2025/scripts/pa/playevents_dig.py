import requests

GAME_PK = 778553
LIMIT = 1 # number of plate appearances to inspect

url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]

print("\n=== PLAYEVENTS STRUCTURE INSPECTION ===\n")

for play in all_plays[:LIMIT]:

    pa_id = play["about"]["atBatIndex"]
    play_events = play.get("playEvents", [])

    print(f"\nPA ID: {pa_id}")
    print(f"Total playEvents: {len(play_events)}")

    for idx, event in enumerate(play_events):

        print(f"\n  Event Index: {idx}")
        print(f"  isPitch: {event.get('isPitch')}")
        print("  Top-Level Keys:", list(event.keys()))

        details = event.get("details", {})
        print("  details keys:", list(details.keys()))

        if event.get("pitchData"):
            print("  pitchData keys:", list(event["pitchData"].keys()))

        if event.get("hitData"):
            print("  hitData keys:", list(event["hitData"].keys()))

    print("-" * 80)