import duckdb
import pandas as pd

conn = duckdb.connect("redsox_25.duckdb")
df = conn.execute('SELECT * FROM "2025_schedule" ORDER BY gameDate').df()
conn.close()
df.to_csv("2025_schedule.csv", index=False)