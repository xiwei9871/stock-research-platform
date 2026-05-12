from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.reports.daily_report_bundle import write_daily_report_bundle
from stock_research.reports.daily_topn_report import write_daily_topn_report
from stock_research.reports.market_state_report import write_market_state_report
from stock_research.reports.position_review_report import (
    generate_position_review,
    write_position_review_report,
)
from stock_research.reports.risk_alert_report import generate_risk_alerts, write_risk_alert_report
from stock_research.reports.sector_strength_report import write_sector_strength_report


def write_daily_research_reports(
    trade_date: str,
    score_version: str,
    top_scores: list[dict[str, Any]],
    market_state: dict[str, Any],
    sector_strength: pd.DataFrame,
    positions: list[dict[str, Any]] | None = None,
    feature_snapshot: pd.DataFrame | None = None,
    output_dir: str | Path = "reports/daily_research",
    industry_system: str = "csrc",
    top_n: int = 30,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    report_paths: dict[str, dict[str, Path]] = {}

    report_paths["topn"] = _path_dict(
        write_daily_topn_report(
            trade_date=trade_date,
            score_version=score_version,
            top_scores=top_scores,
            output_dir=output_path / "topn",
        )
    )
    report_paths["market_state"] = write_market_state_report(
        market_state,
        output_dir=output_path / "market_state",
    )
    report_paths["sector_strength"] = write_sector_strength_report(
        sector_strength,
        trade_date=trade_date,
        industry_system=industry_system,
        output_dir=output_path / "sector_strength",
    )

    risk_alerts = generate_risk_alerts(
        trade_date=trade_date,
        top_scores=top_scores,
        market_state=market_state,
        sector_strength=sector_strength,
        feature_snapshot=feature_snapshot,
    )
    report_paths["risk_alerts"] = write_risk_alert_report(
        risk_alerts,
        trade_date=trade_date,
        output_dir=output_path / "risk_alerts",
    )

    position_review = generate_position_review(
        trade_date=trade_date,
        positions=positions or [],
        top_scores=top_scores,
        market_state=market_state,
        risk_alerts=risk_alerts,
        top_n=top_n,
    )
    report_paths["position_review"] = write_position_review_report(
        position_review,
        trade_date=trade_date,
        output_dir=output_path / "position_review",
    )

    bundle_input = {
        key: paths["markdown_path"]
        for key, paths in report_paths.items()
        if "markdown_path" in paths
    }
    report_paths["bundle"] = write_daily_report_bundle(
        trade_date=trade_date,
        report_paths=bundle_input,
        output_dir=output_path / "daily",
    )
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "report_paths": report_paths,
        "risk_alerts": risk_alerts,
        "position_review": position_review,
    }


def _path_dict(paths: dict[str, str | Path]) -> dict[str, Path]:
    return {key: Path(value) for key, value in paths.items()}
