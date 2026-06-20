from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stock_research.report_run_store import apply_report_run_schema
from stock_research.reports.daily_review_report_workflow import (
    build_daily_review,
    write_daily_review_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.reports.daily_review_report_cli")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--apply-report-run-schema", action="store_true")
    parser.add_argument("--record-run", action="store_true")
    return parser


def load_daily_review_inputs(trade_date: str) -> dict[str, Any]:
    return {
        "data_readiness": {},
        "market_review": {},
        "lhb_review": {},
        "mid_trend_review": {},
        "technical_bottleneck_review": {},
        "holding_reviews": [],
    }


def run_daily_review_report(
    trade_date: str,
    output_root: str | Path,
    apply_report_run_schema_first: bool = False,
    record_run: bool = False,
) -> dict[str, Any]:
    if apply_report_run_schema_first:
        apply_report_run_schema()

    inputs = load_daily_review_inputs(trade_date)
    review = build_daily_review(
        trade_date=trade_date,
        run_id=f"daily_review_v1_{trade_date.replace('-', '')}_2200",
        data_readiness=inputs.get("data_readiness"),
        market_review=inputs.get("market_review"),
        lhb_review=inputs.get("lhb_review"),
        mid_trend_review=inputs.get("mid_trend_review"),
        technical_bottleneck_review=inputs.get("technical_bottleneck_review"),
        holding_reviews=inputs.get("holding_reviews"),
    )
    report_paths = write_daily_review_package(
        review,
        output_root=output_root,
        record_run=record_run,
    )
    return {"review": review, "report_paths": report_paths}


def main(runner=run_daily_review_report) -> None:
    args = build_parser().parse_args()
    result = runner(
        trade_date=args.trade_date,
        output_root=Path(args.output_root),
        apply_report_run_schema_first=args.apply_report_run_schema,
        record_run=args.record_run,
    )
    for key, value in result["report_paths"].items():
        print(f"daily_review_v1|{key}|{value}")


if __name__ == "__main__":
    main()
