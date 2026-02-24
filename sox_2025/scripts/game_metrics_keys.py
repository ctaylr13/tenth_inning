import requests
import json
from collections import defaultdict

URL = "https://statsapi.mlb.com/api/v1/game/776983/withMetrics"

print("Downloading JSON...")
data = requests.get(URL, timeout=60).json()

with open("mlb_game.json", "w") as f:
    json.dump(data, f, indent=2)

# -------------------------------
# Detect map-like dictionaries
# -------------------------------
def is_object_map(d):
    if not isinstance(d, dict) or len(d) < 3:
        return False
    if not all(isinstance(v, dict) for v in d.values()):
        return False

    sample = list(d.values())[:5]
    key_sets = [set(v.keys()) for v in sample]
    return len(set(map(tuple, key_sets))) == 1

# -------------------------------
# Walk JSON and count paths
# -------------------------------
path_counts = defaultdict(int)
parent_counts = defaultdict(int)
max_depth = 0

def walk(obj, path="", depth=1):
    global max_depth
    max_depth = max(max_depth, depth)

    if isinstance(obj, dict):

        if is_object_map(obj):
            map_path = f"{path}.{{object}}" if path else "{object}"
            path_counts[map_path] += 1
            parent_counts[path] += 1

            first = next(iter(obj.values()))
            walk(first, map_path, depth + 1)
            return

        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            path_counts[new_path] += 1
            parent_counts[path] += 1
            walk(v, new_path, depth + 1)

    elif isinstance(obj, list):
        list_path = f"{path}[]"
        path_counts[list_path] += 1
        parent_counts[path] += 1

        for item in obj[:10]:  # sample multiple entries
            walk(item, list_path, depth + 1)

walk(data)

# -------------------------------
# Build frequency report
# -------------------------------
report = []
for path, count in path_counts.items():
    parent = path.rsplit(".", 1)[0] if "." in path else ""
    total = parent_counts.get(parent, 1)
    pct = (count / total) * 100 if total else 0
    report.append((pct, path))

report.sort(reverse=True)

with open("schema_frequency.txt", "w") as f:
    for pct, path in report:
        f.write(f"{pct:6.2f}%  {path}\n")

print("\nSaved frequency report to schema_frequency.txt")
print("Max depth:", max_depth)