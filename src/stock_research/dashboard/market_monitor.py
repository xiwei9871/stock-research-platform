from __future__ import annotations

from typing import Any

from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links


def build_market_monitor_eod(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    top_n: int = 5,
) -> dict[str, Any]:
    summary = load_platform_summary(score_version=score_version, top_n=top_n)
    latest_market_date = str(summary.get("latest_market_date") or "")
    selected_trade_date = trade_date or latest_market_date
    warnings: list[str] = []
    if not selected_trade_date:
        warnings.append("latest complete market date is unavailable")

    topn_preview = list(summary.get("topn_preview") or [])
    reports = load_report_links(selected_trade_date) if selected_trade_date else []

    return {
        "trade_date": selected_trade_date,
        "freshness": {
            "mode": "eod",
            "label": "Last Completed Trading Day",
            "is_realtime": False,
            "latest_market_date": latest_market_date,
            "latest_factor_date": summary.get("latest_factor_date") or "",
            "latest_score_date": summary.get("latest_score_date") or "",
        },
        "coverage": {
            "market_assets": int(summary.get("market_asset_count") or 0),
            "score_assets": int(summary.get("score_asset_count") or 0),
            "factor_count": int(summary.get("factor_count") or 0),
        },
        "market_breadth": {
            "advancers": None,
            "decliners": None,
            "limit_up": None,
            "limit_down": None,
            "advancing_ratio": None,
            "turnover_change_pct": None,
            "status": "pending_source",
        },
        "index_snapshot": [],
        "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
        "unusual_moves": [],
        "watchlist_alerts": [],
        "strategy_signal_summary": {
            "topn_preview_count": len(topn_preview),
            "topn_preview": topn_preview,
            "risk_filter_counts": {},
        },
        "generated_reports": reports[:8],
        "warnings": warnings,
    }
