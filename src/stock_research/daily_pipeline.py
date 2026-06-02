from typing import Any
from pathlib import Path

from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
from stock_research.reports.daily_topn_report import write_daily_topn_report
from stock_research.run_card import write_run_card
from stock_research.services.universe_service import UniverseResult


def run_daily_factor_pipeline(
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    lookback_bars: int = 130,
    reports_dir: str = "/Users/xiwei/stock_research/reports",
    universe_result: UniverseResult | None = None,
) -> dict[str, Any]:
    factor_rows = build_and_store_factor_daily(
        trade_date=trade_date,
        lookback_bars=lookback_bars,
    )
    score_rows = score_stored_factor_daily(
        trade_date=trade_date,
        score_version=score_version,
        approved_only=True,
    )
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
        universe_result=universe_result,
    )
    report_paths = write_daily_topn_report(
        trade_date=trade_date,
        score_version=score_version,
        top_scores=top_scores,
        output_dir=reports_dir,
    )
    run_card = write_run_card(
        output_dir=Path(reports_dir) / "run_card",
        run_type="daily_factor_pipeline",
        run_id=f"daily_factor_pipeline:{trade_date}:{score_version}:top{top_n}",
        title="Daily Factor Pipeline",
        config={
            "trade_date": trade_date,
            "score_version": score_version,
            "top_n": int(top_n),
            "lookback_bars": int(lookback_bars),
        },
        metrics={
            "factor_rows": factor_rows,
            "score_rows": score_rows,
            "top_scores_count": len(top_scores),
        },
        artifact_paths=report_paths,
        warnings=["top_scores_empty"] if not top_scores else [],
        data_coverage={
            "input_start_date": trade_date,
            "input_end_date": trade_date,
            "actual_dates": [trade_date] if top_scores else [],
            "row_count": len(top_scores),
            "asset_count": len({str(row.get("asset_id")) for row in top_scores if row.get("asset_id")}),
        },
    )
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "factor_rows": factor_rows,
        "score_rows": score_rows,
        "top_scores": top_scores,
        "report_paths": report_paths,
        "run_card": run_card,
    }
