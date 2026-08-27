"""Export one legacy DuckDB game as a protobuf artifact."""

import argparse
from pathlib import Path

from artifacts.game_artifact import write_game_artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_pk", type=int)
    parser.add_argument("--database", type=Path, default=Path("redsox_25.duckdb"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output = args.output or Path(f"game-{args.game_pk}.pb")
    byte_count = write_game_artifact(args.database, args.game_pk, output)
    print(f"Wrote game {args.game_pk} to {output} ({byte_count} bytes).")


if __name__ == "__main__":
    main()
