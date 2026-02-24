import requests

GAME_PK = 778553
LIMIT = 5

# i think this is going to have to be done last to get all the different credit types and write the table properly 

# f_assist: 15 occurrences
# f_deflection: 1 occurrences
# f_fielded_ball: 11 occurrences
# f_putout: 54 occurrences
url = f"https://statsapi.mlb.com/api/v1/game/{GAME_PK}/withMetrics"
data = requests.get(url, timeout=60).json()

all_plays = data["liveData"]["plays"]["allPlays"]


for play in all_plays[:LIMIT]:
# for play in all_plays:

    pa_id = play["about"]["atBatIndex"]
    runners = play.get("runners", [])

    print(f"\nPA ID: {pa_id}")
    # print(f"Number of runners: {len(runners)}")

    for i, runner in enumerate(runners):
        # # Credits keys (if present)
        credits = runner.get("credits", [])
        if credits:
            print("    Credits Count:", len(credits))
            # print("    Credit Keys:", list(credits[0].keys()))
            print('credits', credits)
        else:
            print("    Credits: None")

    print("-" * 70)