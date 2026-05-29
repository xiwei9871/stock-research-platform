from typing import Any

from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import load_top_scores_for_dashboard
from stock_research.dashboard.watchlist import load_watchlist_signals_for_dashboard


def build_dashboard_overview(
    trade_date: str,
    score_version: str = "manual_v1",
    watchlist_id: str = "default",
    top_n: int = 30,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "watchlist_id": watchlist_id,
        "top_scores": load_top_scores_for_dashboard(trade_date, score_version, top_n),
        "watchlist_signals": load_watchlist_signals_for_dashboard(watchlist_id, trade_date),
        "reports": load_report_links(trade_date),
    }
