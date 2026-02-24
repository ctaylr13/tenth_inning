import pandas as pd
import duckdb
from typing import Optional

DB_PATH = "../../redsox_25.duckdb"
CSV_PATH = "managers.csv"  # change if needed
TABLE_NAME = "2025_managers"

def clean_pct(x: Optional[str]) -> Optional[float]:
    if pd.isna(x):
        return None
    s = str(x).strip().replace("%", "")
    if s == "":
        return None
    try:
        return float(s) / 100.0
    except Exception:
        return None

def to_int_or_none(x: Optional[str]) -> Optional[int]:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except Exception:
        return None

df = pd.read_csv(CSV_PATH)

df = df.dropna(how="all")

df.columns = [c.strip() for c in df.columns]


if "W-L%" in df.columns:
    df["W-L%"] = df["W-L%"].apply(clean_pct)
if "W-L%post" in df.columns:
    df["W-L%post"] = df["W-L%post"].apply(clean_pct)
for col in ("W","L","Ties","G","Finish","Wpost","Lpost","Challenges","Overturned","Ejections","Rk"):
    if col in df.columns:
        df[col] = df[col].apply(to_int_or_none)

if "Overturn%" in df.columns:
    df["Overturn%"] = df["Overturn%"].apply(clean_pct)

for col in ("Mgr","Tm"):
    if col in df.columns:
        df[col] = df[col].astype(object).where(df[col].notna(), None)

conn = duckdb.connect(DB_PATH)

conn = duckdb.connect(DB_PATH)

conn.register("tmp_managers", df)
conn.execute(f'CREATE OR REPLACE TABLE "{TABLE_NAME}" AS SELECT * FROM tmp_managers')
conn.unregister("tmp_managers")
conn.close()

print(f"Wrote {len(df)} rows to {TABLE_NAME} in {DB_PATH}")

print(f"Wrote {len(df)} rows to {TABLE_NAME} in {DB_PATH}")