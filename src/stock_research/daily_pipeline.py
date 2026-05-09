from typing import Any

from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
from stock_research.reports.daily_topn_report import write_daily_topn_report


def run_daily_factor_pipeline(
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    lookback_bars: int = 130,
    reports_dir: str = "/Users/xiwei/stock_research/reports",
) -> dict[str, Any]:
    factor_rows = build_and_store_factor_daily(
        trade_date=trade_date,
        lookback_bars=lookback_bars,
    )
    score_rows = score_stored_factor_daily(
        trade_date=trade_date,
        score_version=score_version,
    )
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    report_paths = write_daily_topn_report(
        trade_date=trade_date,
        score_version=score_version,
        top_scores=top_scores,
        output_dir=reports_dir,
    )
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "factor_rows": factor_rows,
        "score_rows": score_rows,
        "top_scores": top_scores,
        "report_paths": report_paths,
    }
