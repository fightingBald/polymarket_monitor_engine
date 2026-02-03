from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tests.utils.alert_dataset import build_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build alert dataset from discord logs")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("logs/discord.out.jsonl"),
        help="Path to discord.out.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/alert_dataset.jsonl"),
        help="Dataset output path",
    )
    parser.add_argument(
        "--no-expand-aggregates",
        action="store_true",
        help="Keep aggregate embeds as single records",
    )
    args = parser.parse_args()

    build_dataset(
        input_path=args.input,
        output_path=args.output,
        expand_aggregates=not args.no_expand_aggregates,
    )


if __name__ == "__main__":
    main()
