from fastapi import FastAPI, HTTPException

from stock_research.dashboard.bars import load_daily_bars, load_minute_bars
from stock_research.dashboard.decisions import load_asset_decision_history
from stock_research.dashboard.overview import build_dashboard_overview
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
    load_top_scores_for_dashboard,
    search_assets,
)
from stock_research.dashboard.watchlist import (
    load_asset_watchlist_signals_for_dashboard,
    load_watchlist_signals_for_dashboard,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Research Dashboard API")

    @app.get("/api/dashboard/overview")
    def dashboard_overview(
        trade_date: str,
        score_version: str = "manual_v1",
        watchlist_id: str = "default",
        top_n: int = 30,
    ):
        return build_dashboard_overview(trade_date, score_version, watchlist_id, top_n)

    @app.get("/api/assets/search")
    def assets_search(q: str, limit: int = 20):
        return {"items": search_assets(q, limit)}

    @app.get("/api/assets/{asset_id}")
    def asset_detail(asset_id: str):
        asset = load_asset_detail(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset

    @app.get("/api/assets/{asset_id}/bars")
    def asset_daily_bars(
        asset_id: str,
        start_date: str,
        end_date: str,
        adjust_type: str = "qfq",
    ):
        return {
            "asset_id": asset_id,
            "resolution": "1D",
            "items": load_daily_bars(asset_id, start_date, end_date, adjust_type),
        }

    @app.get("/api/assets/{asset_id}/minute-bars")
    def asset_minute_bars(
        asset_id: str,
        start_time: str,
        end_time: str,
        freq: str = "5min",
        adjust_type: str = "qfq",
        source: str = "baostock",
    ):
        return {
            "asset_id": asset_id,
            "resolution": freq,
            "items": load_minute_bars(
                asset_id,
                start_time,
                end_time,
                freq,
                adjust_type,
                source,
            ),
        }

    @app.get("/api/assets/{asset_id}/scores")
    def asset_score(asset_id: str, trade_date: str, score_version: str = "manual_v1"):
        return {
            "asset_id": asset_id,
            "item": load_asset_score_for_dashboard(asset_id, trade_date, score_version),
        }

    @app.get("/api/assets/{asset_id}/signals")
    def asset_signals(asset_id: str, trade_date: str):
        return {
            "asset_id": asset_id,
            "items": load_asset_watchlist_signals_for_dashboard(asset_id, trade_date),
        }

    @app.get("/api/assets/{asset_id}/decisions")
    def asset_decisions(
        asset_id: str,
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "asset_id": asset_id,
            "items": load_asset_decision_history(asset_id, start_date, end_date, limit),
        }

    @app.get("/api/assets/{asset_id}/outcomes")
    def asset_outcomes(
        asset_id: str,
        start_date: str,
        end_date: str,
        review_session_id: str | None = None,
        limit: int = 20,
    ):
        return {
            "asset_id": asset_id,
            "items": load_asset_outcome_history(
                asset_id,
                start_date,
                end_date,
                review_session_id,
                limit,
            ),
        }

    @app.get("/api/topn")
    def topn(trade_date: str, score_version: str = "manual_v1", top_n: int = 30):
        return {
            "trade_date": trade_date,
            "score_version": score_version,
            "items": load_top_scores_for_dashboard(trade_date, score_version, top_n),
        }

    @app.get("/api/watchlists/{watchlist_id}")
    def watchlist_signals(watchlist_id: str, trade_date: str):
        return {
            "watchlist_id": watchlist_id,
            "trade_date": trade_date,
            "items": load_watchlist_signals_for_dashboard(watchlist_id, trade_date),
        }

    @app.get("/api/reports")
    def reports(trade_date: str):
        return {"trade_date": trade_date, "items": load_report_links(trade_date)}

    return app


app = create_app()
