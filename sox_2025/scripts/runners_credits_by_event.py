import json
from collections import defaultdict

INPUT_FILE = "runners_credits_analysis.json"
OUTPUT_FILE = "credit_value_groups.json"

with open(INPUT_FILE, "r") as f:
    data = json.load(f)

grouped = defaultdict(list)

for event_type, info in data.items():

    credits = info.get("unique_credit_values", [])

    if not credits:
        signature = "EMPTY"
    else:
        # Normalize ordering so matching sets group correctly
        signature = "|".join(sorted(credits))

    grouped[signature].append(event_type)

# Sort event types inside each group
for key in grouped:
    grouped[key] = sorted(grouped[key])

with open(OUTPUT_FILE, "w") as f:
    json.dump(grouped, f, indent=2)

print("Grouped credit values written to credit_value_groups.json")