import duckdb
import pandas as pd

DB_PATH = "../../redsox_25.duckdb"

# ------------------------------------------------------------
# 1️⃣ Load data
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
# 2️⃣ Generate series_id
# ------------------------------------------------------------

series_ids = []
current_series_id = None
current_pair = None

for _, row in df.iterrows():

    pair = (row["home_team_id"], row["away_team_id"])

    if pair != current_pair:
        current_series_id = None
        current_pair = pair

    if row["seriesGameNumber"] == 1:
        current_series_id = row["gamePk"]

    if current_series_id is None:
        current_series_id = row["gamePk"]

    series_ids.append(current_series_id)

df["series_id"] = series_ids

print("Series IDs generated.")

# ------------------------------------------------------------
# 3️⃣ Write series_id back to game table
# ------------------------------------------------------------

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        ALTER TABLE main."2025_game_info"
        ADD COLUMN IF NOT EXISTS series_id BIGINT;
    """)

    con.register("series_update_df", df[["gamePk", "series_id"]])

    con.execute("""
        UPDATE main."2025_game_info" g
        SET series_id = s.series_id
        FROM series_update_df s
        WHERE g.gamePk = s.gamePk;
    """)

print("series_id written to 2025_game_info.")

# ------------------------------------------------------------
# 4️⃣ Build series_dim
# ------------------------------------------------------------

series_dim = (
    df.groupby("series_id")
    .agg(
        season_year=("officialDate", lambda x: pd.to_datetime(x).dt.year.iloc[0]),
        home_team_id=("home_team_id", "first"),
        away_team_id=("away_team_id", "first"),
        series_start_date=("officialDate", "min"),
        series_end_date=("officialDate", "max"),
        games_in_series=("gamePk", "count"),
        scheduled_games=("gamesInSeries", "first"),
    )
    .reset_index()
)

series_dim["is_postseason"] = False

print(f"Built series_dim with {len(series_dim)} series.")

# ------------------------------------------------------------
# 5️⃣ Create / Replace series_dim
# ------------------------------------------------------------

with duckdb.connect(DB_PATH) as con:

    con.execute("""
        CREATE TABLE IF NOT EXISTS series_dim (
            series_id          BIGINT PRIMARY KEY,
            season_year        INTEGER,
            home_team_id       INTEGER,
            away_team_id       INTEGER,
            series_start_date  DATE,
            series_end_date    DATE,
            games_in_series    INTEGER,
            scheduled_games    INTEGER,
            is_postseason      BOOLEAN
        );
    """)

    con.execute("DELETE FROM series_dim;")

    con.register("series_dim_df", series_dim)

    con.execute("""
        INSERT INTO series_dim
        SELECT * FROM series_dim_df;
    """)

print("series_dim successfully created.")

# ------------------------------------------------------------
# 6️⃣ Validation
# ------------------------------------------------------------

with duckdb.connect(DB_PATH) as con:
    series_count = con.execute("""
        SELECT COUNT(*) FROM series_dim
    """).fetchone()[0]

    distinct_series = con.execute("""
        SELECT COUNT(DISTINCT series_id)
        FROM main."2025_game_info"
    """).fetchone()[0]

print("Series_dim rows:", series_count)
print("Distinct series_ids in games:", distinct_series)