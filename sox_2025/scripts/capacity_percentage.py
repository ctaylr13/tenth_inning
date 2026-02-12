import time
import pandas as pd
import duckdb
from typing import Optional

DB_PATH = "../../redsox_25.duckdb"  # adjust if needed
SLEEP_SECONDS = 0.1

conn = duckdb.connect(DB_PATH)

# load schedule rows
sched_q = 'SELECT gamePk, home_venue_id, attendance FROM redsox_25.main."2025_schedule"'
df_sched = conn.execute(sched_q).fetchdf()

if df_sched.empty:
    print("No schedule rows found.")
    conn.close()
    raise SystemExit(0)

# load capacity per venue (use MAX in case multiple games per venue)
cap_q = """
SELECT CAST(venue_id AS INTEGER) AS venue_id,
       MAX(CAST(capacity AS INTEGER)) AS capacity
FROM redsox_25.main.venue_game_stats
WHERE venue_id IS NOT NULL AND capacity IS NOT NULL
GROUP BY venue_id
"""
df_cap = conn.execute(cap_q).fetchdf()

# merge and compute fill_frac
df = df_sched.merge(df_cap, how="left", left_on="home_venue_id", right_on="venue_id")

def compute_fill_frac(att: Optional[int], cap: Optional[int]) -> Optional[float]:
    try:
        if att is None or cap is None:
            return None
        if int(cap) == 0:
            return None
        return float(att) / float(cap)
    except Exception:
        return None

df["fill_frac"] = df.apply(lambda r: compute_fill_frac(r["attendance"], r["capacity"]), axis=1)

updates = df[["gamePk", "fill_frac"]].copy()
if updates.empty:
    print("No fill_frac values computed; nothing to update.")
    conn.close()
    raise SystemExit(0)

# add column if missing
cols = [r[0] for r in conn.execute('PRAGMA table_info(redsox_25.main."2025_schedule")').fetchall()]
if "fill_frac" not in cols:
    conn.execute('ALTER TABLE redsox_25.main."2025_schedule" ADD COLUMN fill_frac DOUBLE')
    print("Added column fill_frac")

# perform update via temp table
conn.register("tmp_fill_updates", updates)
conn.execute("""
CREATE TEMPORARY TABLE tmp_fill AS
SELECT CAST(gamePk AS BIGINT) AS gamePk,
       CAST(fill_frac AS DOUBLE) AS fill_frac
FROM tmp_fill_updates
""")
conn.execute('''
UPDATE redsox_25.main."2025_schedule" AS s
SET fill_frac = u.fill_frac
FROM tmp_fill u
WHERE s.gamePk = u.gamePk
''')
conn.unregister("tmp_fill_updates")

print("Updated fill_frac for", len(updates), "rows (NULL where capacity/attendance missing).")
conn.close()
