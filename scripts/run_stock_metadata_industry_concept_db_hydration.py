from __future__ import annotations

import argparse
from pathlib import Path

from stock_research.stock_metadata_db_hydration import run_stock_metadata_db_hydration


def main() -> None:
    parser = argparse.ArgumentParser(description="Hydrate and audit stock industry/concept metadata in the research DB.")
    parser.add_argument("--as-of-date", default="2026-07-08")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/research/stock_metadata_industry_concept_db_hydration_v1"),
    )
    parser.add_argument("--service", default="stock_research")
    parser.add_argument("--sync-industry", action="store_true")
    parser.add_argument("--sync-concept", action="store_true")
    parser.add_argument("--max-concepts", type=int)
    args = parser.parse_args()
    summary = run_stock_metadata_db_hydration(
        as_of_date=args.as_of_date,
        output_dir=args.output_dir,
        sync_industry=args.sync_industry,
        sync_concept=args.sync_concept,
        max_concepts=args.max_concepts,
        service=args.service,
    )
    print(summary)


if __name__ == "__main__":
    main()

