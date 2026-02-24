import requests
import json
import re
from collections import defaultdict

URL = "https://statsapi.mlb.com/api/v1/game/776983/withMetrics"

print("Downloading JSON...")
data = requests.get(URL, timeout=60).json()

with open("mlb_game.json", "w") as f:
    json.dump(data, f, indent=2)

print("Saved raw response to mlb_game.json")

# ---------------------------------------------------
# IDENTIFIER DETECTION
# ---------------------------------------------------

def looks_like_identifier(key):
    """
    Detect keys that represent database IDs instead of schema fields
    Always returns True/False (never None)
    """

    if not isinstance(key, str):
        key = str(key)

    if len(key) == 0:
        return False

    digit_ratio = sum(c.isdigit() for c in key) / len(key)

    return bool(
        digit_ratio > 0.3 or                 # many numbers
        re.fullmatch(r"[A-Z]*\d+", key) or   # ID12345
        re.fullmatch(r"\d+", key)            # 123456
    )

def is_object_map(d):
    """
    True if dict behaves like {id: object, id: object}
    """
    if not isinstance(d, dict) or len(d) < 2:
        return False

    keys = list(d.keys())

    id_like = sum(looks_like_identifier(k) for k in keys)

    # majority of keys look like identifiers
    if id_like / len(keys) < 0.6:
        return False

    # values should be objects
    if not all(isinstance(v, dict) for v in d.values()):
        return False

    return True

# ---------------------------------------------------
# WALK JSON + COUNT FREQUENCY
# ---------------------------------------------------

path_counts = defaultdict(int)
parent_counts = defaultdict(int)
max_depth = 0

def walk(obj, path="", depth=1):
    global max_depth
    max_depth = max(max_depth, depth)

    # ---------- OBJECT ----------
    if isinstance(obj, dict):

        # collapse ID-maps
        if is_object_map(obj):
            map_path = f"{path}.{{object}}" if path else "{object}"
            path_counts[map_path] += 1
            parent_counts[path] += 1

            # analyze ONE representative child
            first = next(iter(obj.values()))
            walk(first, map_path, depth + 1)
            return

        # normal object
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            path_counts[new_path] += 1
            parent_counts[path] += 1
            walk(v, new_path, depth + 1)

    # ---------- ARRAY ----------
    elif isinstance(obj, list):
        list_path = f"{path}[]"
        path_counts[list_path] += 1
        parent_counts[path] += 1

        # analyze ALL items (important for MLB)
        for item in obj:
            walk(item, list_path, depth + 1)

# run analysis
walk(data)

# ---------------------------------------------------
# BUILD FREQUENCY REPORT
# ---------------------------------------------------

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

print("\nSaved normalized schema to schema_frequency.txt")
print("Max nesting depth:", max_depth)
print("Total unique schema paths:", len(report))