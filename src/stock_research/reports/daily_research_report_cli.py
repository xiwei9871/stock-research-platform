import argparse
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_store import load_top_scores
from stock_research.reports.daily_research_report_workflow import write_daily_research_reports
from stock_research.reports.market_state_report import calc_market_state, load_market_state_bars
from stock_research.reports.sector_strength_report import (
    calc_sector_strength,
    load_sector_strength_bars,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.reports.daily_research_report_cli")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--index-id", default="CSI300")
    parser.add_argument("--market-lookback-days", type=int, default=90)
    parser.add_argument("--industry-system", default="csrc")
    parser.add_argument("--sector-lookback-days", type=int, default=60)
    parser.add_argument("--positions-csv")
    parser.add_argument("--reports-dir", default="/Users/xiwei/stock_research/reports")
    return parser


def run_daily_research_report(
    trade_date: str,
    score_version: str,
    top_n: int,
    index_id: str,
    market_lookback_days: int,
    industry_system: str,
    sector_lookback_days: int,
    positions_csv: str | None,
    reports_dir: str | Path,
) -> dict[str, Any]:
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    asset_ids = [str(row.get("asset_id")) for row in top_scores if row.get("asset_id")]
    top_scores = enrich_top_scores_with_industry(
        top_scores,
        load_industry_memberships(
            trade_date=trade_date,
            asset_ids=asset_ids,
            industry_system=industry_system,
        ),
    )
    market_start = _lookback_start(trade_date, market_lookback_days)
    market_bars = load_market_state_bars(
        start_date=market_start,
        end_date=trade_date,
        index_id=index_id,
    )
    market_state = calc_market_state(market_bars, trade_date=trade_date, index_id=index_id)

    sector_start = _lookback_start(trade_date, sector_lookback_days)
    sector_bars = load_sector_strength_bars(
        start_date=sector_start,
        end_date=trade_date,
        industry_system=industry_system,
    )
    sector_strength = calc_sector_strength(sector_bars, trade_date=trade_date, top_n=top_n)
    positions = _load_positions_csv(positions_csv)
    feature_snapshot = load_feature_snapshot(trade_date=trade_date, asset_ids=asset_ids)
    return write_daily_research_reports(
        trade_date=trade_date,
        score_version=score_version,
        top_scores=top_scores,
        market_state=market_state,
        sector_strength=sector_strength,
        positions=positions,
        feature_snapshot=feature_snapshot,
        output_dir=reports_dir,
        industry_system=industry_system,
        top_n=top_n,
    )


def load_industry_memberships(
    trade_date: str,
    asset_ids: list[str],
    industry_system: str,
    service: str = SETTINGS.research_service,
) -> dict[str, dict[str, Any]]:
    if not asset_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT
            asset_id,
            industry_code,
            industry_name,
            level
        FROM core.industry_membership
        WHERE industry_system = %s
          AND start_date <= %s
          AND (end_date IS NULL OR end_date >= %s)
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, level, start_date DESC
    """
    params = [industry_system, trade_date, trade_date, *asset_ids]
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)

    memberships: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset_id = str(row["asset_id"])
        if asset_id in memberships:
            continue
        memberships[asset_id] = {
            "industry_code": row.get("industry_code"),
            "industry_name": row.get("industry_name"),
            "industry_level": row.get("level"),
        }
    return memberships


def enrich_top_scores_with_industry(
    top_scores: list[dict[str, Any]],
    memberships: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for row in top_scores:
        asset_id = str(row.get("asset_id", ""))
        merged = dict(row)
        if asset_id in memberships:
            merged.update(memberships[asset_id])
        enriched.append(merged)
    return enriched


def load_feature_snapshot(
    trade_date: str,
    asset_ids: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not asset_ids:
        return pd.DataFrame(columns=["asset_id", "feature_name", "feature_value"])
    placeholders = ", ".join(["%s"] * len(asset_ids))
    sql = f"""
        SELECT asset_id, feature_name, feature_value
        FROM feature_snapshot
        WHERE trade_date = %s
          AND feature_set = 'p0_daily'
          AND feature_version = 'v1'
          AND asset_id IN ({placeholders})
        ORDER BY asset_id, feature_name
    """
    params = [trade_date, *asset_ids]
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def main(runner=run_daily_research_report) -> None:
    args = build_parser().parse_args()
    result = runner(
        trade_date=args.trade_date,
        score_version=args.score_version,
        top_n=args.top_n,
        index_id=args.index_id,
        market_lookback_days=args.market_lookback_days,
        industry_system=args.industry_system,
        sector_lookback_days=args.sector_lookback_days,
        positions_csv=args.positions_csv,
        reports_dir=Path(args.reports_dir),
    )
    report_paths = result["report_paths"]
    for key in ("bundle", "topn", "market_state", "sector_strength", "risk_alerts", "position_review"):
        print(f"daily_research_report|{key}|{report_paths[key]['markdown_path']}")


def _load_positions_csv(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    return pd.read_csv(path).to_dict("records")


def _lookback_start(trade_date: str, days: int) -> str:
    return (pd.Timestamp(trade_date) - timedelta(days=days)).date().isoformat()


if __name__ == "__main__":
    main()
