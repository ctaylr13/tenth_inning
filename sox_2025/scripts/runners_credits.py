import duckdb
import requests
import json
from collections import defaultdict

DB_PATH = "../../redsox_25.duckdb"

query = """
WITH ranked_events AS (
    SELECT
        game_pk,
        pa_id,
        eventType,
        ROW_NUMBER() OVER (
            PARTITION BY eventType
            ORDER BY game_pk
        ) AS rn
    FROM main."2025_game_plate_appearance"
)
SELECT
    game_pk,
    pa_id,
    eventType
FROM ranked_events
WHERE rn <= 2
ORDER BY eventType, game_pk;
"""

with duckdb.connect(DB_PATH) as con:
    rows = con.execute(query).fetchall()

print(f"Found {len(rows)} sample plate appearances.")

results = defaultdict(list)

for game_pk, pa_id, event_type in rows:

    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/withMetrics"
    data = requests.get(url, timeout=60).json()

    all_plays = data["liveData"]["plays"]["allPlays"]

    for play in all_plays:
        if play["about"]["atBatIndex"] == pa_id:

            # Preserve ORIGINAL runners array exactly as-is
            original_runners = play.get("runners", [])

            results[event_type].append({
                "game_pk": game_pk,
                "pa_id": pa_id,
                "runners_credits": original_runners
            })

            break

print("Extraction complete.")

with open("runners_credits_schema.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved to runners_credits_schema.json")