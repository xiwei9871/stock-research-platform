#!/usr/bin/env python3
from __future__ import annotations

import argparse

from stock_research.tech_bottleneck_review_universe_yanbaoke_report_backfill import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_UNIVERSE_PATH,
    run_tech_bottleneck_review_universe_yanbaoke_report_backfill,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Yanbaoke broker-report PDFs for review-universe report gaps.")
    parser.add_argument("--universe-path", default=str(DEFAULT_UNIVERSE_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-reports-per-stock", type=int, default=1)
    parser.add_argument("--max-missing-stocks", type=int)
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default="2026-07-09")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=3.0)
    args = parser.parse_args()

    result = run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
        universe_path=args.universe_path,
        output_dir=args.output_dir,
        max_reports_per_stock=args.max_reports_per_stock,
        max_missing_stocks=args.max_missing_stocks,
        start_date=args.start_date,
        end_date=args.end_date,
        sleep_seconds=args.sleep_seconds,
        retry_attempts=args.retry_attempts,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )
    summary = result["summary"]
    print(f"review_universe_yanbaoke_report_backfill|output_dir|{args.output_dir}")
    print(f"review_universe_yanbaoke_report_backfill|review_universe_count|{summary['review_universe_count']}")
    print(f"review_universe_yanbaoke_report_backfill|existing_report_pdf_covered|{summary['existing_report_pdf_covered_count']}")
    print(f"review_universe_yanbaoke_report_backfill|missing_before|{summary['missing_report_pdf_before_count']}")
    print(f"review_universe_yanbaoke_report_backfill|downloaded_stock_count|{summary['downloaded_stock_count']}")
    print(f"review_universe_yanbaoke_report_backfill|unresolved_missing|{summary['unresolved_missing_report_pdf_count']}")
    print(f"review_universe_yanbaoke_report_backfill|acceptance_decision|{summary['acceptance_decision']}")


if __name__ == "__main__":
    main()
