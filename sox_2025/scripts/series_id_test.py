import duckdb
import pandas as pd

DB_PATH = "../../redsox_25.duckdb"

# ------------------------------------------------------------
# 1️⃣ Load data (NO updates)
# ------------------------------------------------------------

with duckdb.connect(DB_PATH) as con:
    df = con.execute("""
        SELECT
            gamePk,
            officialDate,
            home_team_id,
            away_team_id,
            seriesGameNumber,
            gamesInSeries
        FROM main."2025_game_info"
        ORDER BY
            home_team_id,
            away_team_id,
            officialDate,
            seriesGameNumber,
            gamePk
    """).fetchdf()

print(f"Loaded {len(df)} rows")

# ------------------------------------------------------------
# 2️⃣ Generate series_id (test only)
# ------------------------------------------------------------

series_ids = []
current_series_id = None
current_pair = None

for _, row in df.iterrows():

    pair = (row["home_team_id"], row["away_team_id"])

    # New matchup → reset
    if pair != current_pair:
        current_series_id = None
        current_pair = pair

    # Start of new series
    if row["seriesGameNumber"] == 1:
        current_series_id = row["gamePk"]

    # Safety: if still None, flag
    if current_series_id is None:
        print("⚠ WARNING — seriesGameNumber != 1 at start of matchup:")
        print(row)
        current_series_id = row["gamePk"]  # allow continuation

    series_ids.append(current_series_id)

df["series_id"] = series_ids

print("Series IDs generated (test mode).")

# ------------------------------------------------------------
# 3️⃣ Inspect series grouping
# ------------------------------------------------------------

series_summary = (
    df.groupby("series_id")
    .agg(
        home_team_id=("home_team_id", "first"),
        away_team_id=("away_team_id", "first"),
        start_date=("officialDate", "min"),
        end_date=("officialDate", "max"),
        games=("gamePk", "count"),
    )
    .reset_index()
)

print("\nSeries size distribution:")
print(series_summary["games"].value_counts().sort_index())

print("\nSample series:")
print(series_summary.head(10))

# ------------------------------------------------------------
# 4️⃣ Spot-check one matchup manually
# ------------------------------------------------------------

print("\nExample matchup check:")
example_pair = df.iloc[0][["home_team_id", "away_team_id"]].tolist()

print(
    df[
        (df["home_team_id"] == example_pair[0]) &
        (df["away_team_id"] == example_pair[1])
    ][["gamePk", "officialDate", "seriesGameNumber", "series_id"]]
)