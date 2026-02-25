import json
from collections import defaultdict

INPUT_FILE = "runners_credits_schema.json"
OUTPUT_FILE = "runners_credits_analysis.json"

# ----------------------------------------------------
# Expected credit object keys
# ----------------------------------------------------
EXPECTED_TOP_KEYS = {"player", "position", "credit"}
EXPECTED_PLAYER_KEYS = {"id", "link"}
EXPECTED_POSITION_KEYS = {"code", "name", "type", "abbreviation"}

with open(INPUT_FILE, "r") as f:
    data = json.load(f)

analysis = {}

for event_type, samples in data.items():

    total_samples = len(samples)
    empty_credit_arrays = 0
    non_empty_credit_arrays = 0
    unique_credit_values = set()
    shape_valid = True

    for sample in samples:
        runners = sample.get("runners_credits", [])

        for runner in runners:

            credits = runner.get("credits", [])

            if not credits:
                empty_credit_arrays += 1
                continue

            non_empty_credit_arrays += 1

            for credit_obj in credits:

                # Track unique credit types
                if "credit" in credit_obj:
                    unique_credit_values.add(credit_obj["credit"])

                # Validate shape
                if set(credit_obj.keys()) != EXPECTED_TOP_KEYS:
                    shape_valid = False
                    continue

                if set(credit_obj["player"].keys()) != EXPECTED_PLAYER_KEYS:
                    shape_valid = False

                if set(credit_obj["position"].keys()) != EXPECTED_POSITION_KEYS:
                    shape_valid = False

    analysis[event_type] = {
        "total_samples": total_samples,
        "empty_credit_arrays": empty_credit_arrays,
        "non_empty_credit_arrays": non_empty_credit_arrays,
        "unique_credit_values": sorted(unique_credit_values),
        "credit_shape_valid": shape_valid
    }

# ----------------------------------------------------
# Write Results
# ----------------------------------------------------

with open(OUTPUT_FILE, "w") as f:
    json.dump(analysis, f, indent=2)

print("Analysis written to runners_credits_analysis.json")