from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from stock_research.concept_daily_backfill import backfill_concept_daily_bars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill THS concept daily bars")
    parser.add_argument("--service", default="stock_research")
    parser.add_argument("--concept-system", default="ths")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concept-name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = backfill_concept_daily_bars(
        service=args.service,
        concept_system=args.concept_system,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
        workers=args.workers,
        offset=args.offset,
        limit=args.limit,
        concept_name=args.concept_name,
        dry_run=args.dry_run,
    )
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if args.report_path:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not summary["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
