import duckdb
import pandas as pd

conn = duckdb.connect("redsox_25.duckdb")
df = conn.execute('SELECT * FROM "2025_schedule" ORDER BY gameDate').df()
conn.close()

# Ensure gameDate is parsed as UTC-aware, then format to ISO Zulu
df["gameDate"] = pd.to_datetime(df["gameDate"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

df.to_json("2025_schedule.json", orient="records", indent=2)
print("Wrote", len(df), "records to 2025_schedule.json")
