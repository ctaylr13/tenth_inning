import time, json, requests, pandas as pd, duckdb
from typing import Dict, Any

DB_PATH = "../../redsox_25.duckdb"
GAME_URL = "https://statsapi.mlb.com/api/v1/game/{pk}/withMetrics"
TIMEOUT = 30
SLEEP_SECONDS = 0.1
USER_AGENT = "tenth-inning-script/1.0 (6282920+ctaylr13@users.noreply.github.com)"

def safe_get(d: Dict[Any, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
conn = duckdb.connect(DB_PATH)

game_pks = conn.execute('SELECT DISTINCT gamePk FROM "2025_schedule"').fetchdf()["gamePk"].astype(int).tolist()

def get_side_arrays(section, name):
    if not isinstance(section, dict):
        return None, None
    away = section.get("away", {}) and section["away"].get(name) or []
    home = section.get("home", {}) and section["home"].get(name) or []
    # ensure lists
    away = away if isinstance(away, list) else []
    home = home if isinstance(home, list) else []
    return home, away

rows = []
total = len(game_pks)
for i, pk in enumerate(game_pks, start=1):
    try:
        r = session.get(GAME_URL.format(pk=pk), timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[{i}/{total}] fetch error {pk}: {e}")
        time.sleep(SLEEP_SECONDS)
        continue

    # candidate team sections
    candidates = [
        safe_get(payload, "gameData", "teams"),
        safe_get(payload, "teams"),
        safe_get(payload, "liveData", "boxscore", "teams")
    ]

    batters_home = batters_away = []
    pitchers_home = pitchers_away = []
    bench_home = bench_away = []
    bullpen_home = bullpen_away = []
    battingOrder_home = battingOrder_away = []

    for sec in candidates:
        if not isinstance(sec, dict):
            continue
        if not (batters_home or batters_away):
            batters_home, batters_away = get_side_arrays(sec, "batters")
        if not (pitchers_home or pitchers_away):
            pitchers_home, pitchers_away = get_side_arrays(sec, "pitchers")
        if not (bench_home or bench_away):
            bench_home, bench_away = get_side_arrays(sec, "bench")
        if not (bullpen_home or bullpen_away):
            bullpen_home, bullpen_away = get_side_arrays(sec, "bullpen")
        if not (battingOrder_home or battingOrder_away):
            battingOrder_home, battingOrder_away = get_side_arrays(sec, "battingOrder")

    # final fallbacks (top-level locations)
    if not (batters_home or batters_away):
        bo = safe_get(payload, "gameData", "batters") or safe_get(payload, "batters")
        if isinstance(bo, list):
            # ambiguous top-level list -> treat as combined away
            batters_away = bo
    if not (pitchers_home or pitchers_away):
        po = safe_get(payload, "gameData", "pitchers") or safe_get(payload, "pitchers")
        if isinstance(po, list):
            pitchers_away = po
    if not (bench_home or bench_away):
        be = safe_get(payload, "gameData", "bench") or safe_get(payload, "bench")
        if isinstance(be, list):
            bench_away = be
    if not (bullpen_home or bullpen_away):
        bu = safe_get(payload, "gameData", "bullpen") or safe_get(payload, "bullpen")
        if isinstance(bu, list):
            bullpen_away = bu
    if not (battingOrder_home or battingOrder_away):
        bo2 = safe_get(payload, "gameData", "battingOrder") or safe_get(payload, "battingOrder")
        if isinstance(bo2, list):
            battingOrder_away = bo2

    rows.append({
        "gamePk": int(pk),
        "batters_home": json.dumps(batters_home),
        "batters_away": json.dumps(batters_away),
        "pitchers_home": json.dumps(pitchers_home),
        "pitchers_away": json.dumps(pitchers_away),
        "bench_home": json.dumps(bench_home),
        "bench_away": json.dumps(bench_away),
        "bullpen_home": json.dumps(bullpen_home),
        "bullpen_away": json.dumps(bullpen_away),
        "battingOrder_home": json.dumps(battingOrder_home),
        "battingOrder_away": json.dumps(battingOrder_away)
    })

    print(f"[{i}/{total}] {pk} batters_home={len(batters_home)} batters_away={len(batters_away)} battingOrder_home={len(battingOrder_home)} battingOrder_away={len(battingOrder_away)}")
    time.sleep(SLEEP_SECONDS)

if not rows:
    print("No rows collected.")
    conn.close()
    raise SystemExit(0)

df = pd.DataFrame(rows)

conn.execute("""
CREATE TABLE IF NOT EXISTS game_roles (
  gamePk BIGINT PRIMARY KEY,
  batters_home VARCHAR,
  batters_away VARCHAR,
  pitchers_home VARCHAR,
  pitchers_away VARCHAR,
  bench_home VARCHAR,
  bench_away VARCHAR,
  bullpen_home VARCHAR,
  bullpen_away VARCHAR,
  battingOrder_home VARCHAR,
  battingOrder_away VARCHAR
)
""")

gamepk_list = ",".join(str(int(x)) for x in sorted(df["gamePk"].unique()))
if gamepk_list:
    conn.execute(f"DELETE FROM game_roles WHERE gamePk IN ({gamepk_list})")

conn.register("tmp_roles", df)
conn.execute("""
INSERT INTO game_roles
SELECT CAST(gamePk AS BIGINT),
       batters_home, batters_away,
       pitchers_home, pitchers_away,
       bench_home, bench_away,
       bullpen_home, bullpen_away,
       battingOrder_home, battingOrder_away
FROM tmp_roles
""")
conn.unregister("tmp_roles")

print("Inserted", len(df), "rows into game_roles")
conn.close()
