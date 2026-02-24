import requests
from collections import defaultdict

GAME_PK = 778553

url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]

credit_type_counts = defaultdict(int)

for play in all_plays:

    runners = play.get("runners", [])

    for runner in runners:
        credits = runner.get("credits", [])

        for credit in credits:
            credit_type = credit.get("credit")
            if credit_type:
                credit_type_counts[credit_type] += 1

# ---------------------------------------------------
# Print Results
# ---------------------------------------------------
print("\n=== UNIQUE FIELDING CREDIT TYPES ===\n")

for credit_type in sorted(credit_type_counts.keys()):
    print(f"{credit_type}: {credit_type_counts[credit_type]} occurrences")