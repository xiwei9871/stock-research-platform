from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.backtests import (
    list_backtest_strategies,
    run_backtest,
    run_fresh_backtest,
    run_replay_backtest,
)
from stock_research.dashboard.bars import load_daily_bars, load_minute_bars
from stock_research.dashboard.decisions import load_asset_decision_history
from stock_research.dashboard.experiment_proposals import load_experiment_proposals_summary
from stock_research.dashboard.experiment_replay import load_experiment_replay_summary
from stock_research.dashboard.factors import (
    build_factor_score_preview,
    list_factor_library,
    parse_factor_selection,
)
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.news import (
    load_asset_news,
    load_public_news_for_dashboard,
    refresh_public_news_for_dashboard,
)
from stock_research.dashboard.news_scheduler import (
    NEWS_SCHEDULER_INTERVAL_SECONDS,
    PublicNewsScheduler,
    scheduler_enabled_from_env,
)
from stock_research.dashboard.overview import build_dashboard_overview
from stock_research.dashboard.outcome_analytics import load_outcome_analytics_summary
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import (
    list_research_reports,
    load_asset_research_reports,
    load_research_report_summary,
)
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
    load_top_scores_for_dashboard,
    search_assets,
)
from stock_research.dashboard.search import load_global_search
from stock_research.dashboard.shadow_outcomes import load_shadow_outcomes_summary
from stock_research.dashboard.shadow_analytics_review import load_shadow_analytics_review_summary
from stock_research.dashboard.shadow_outcome_analytics import load_shadow_outcome_analytics_summary
from stock_research.dashboard.shadow_review_decisions import load_shadow_review_decision_summary
from stock_research.dashboard.shadow_follow_up_queue import load_shadow_follow_up_queue_summary
from stock_research.dashboard.shadow_follow_up_resolution import load_shadow_follow_up_resolution_summary
from stock_research.dashboard.shadow_watchlist import load_shadow_watchlist_summary
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.dashboard.strategy_validation import (
    build_strategy_validation_replay,
    list_strategy_validation_artifacts,
    list_strategy_validation_metrics,
    list_strategy_validation_positions,
    list_strategy_validation_runs,
    list_strategy_validation_signals,
    list_strategy_validation_trades,
    load_strategy_validation_run,
)
from stock_research.dashboard.watchlist import (
    load_asset_watchlist_signals_for_dashboard,
    load_watchlist_signals_for_dashboard,
)

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = app.state.public_news_scheduler
        if scheduler.enabled:
            scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title="Stock Research Dashboard API", lifespan=lifespan)
    app.state.public_news_scheduler = PublicNewsScheduler(
        refresh_public_news_for_dashboard,
        interval_seconds=NEWS_SCHEDULER_INTERVAL_SECONDS,
        enabled=scheduler_enabled_from_env(),
    )

    @app.get("/api/dashboard/overview")
    def dashboard_overview(
        trade_date: str,
        score_version: str = "manual_v1",
        watchlist_id: str = "default",
        top_n: int = 30,
    ):
        return build_dashboard_overview(trade_date, score_version, watchlist_id, top_n)

    @app.get("/api/platform/summary")
    def platform_summary(score_version: str = "manual_v1", top_n: int = 5):
        return load_platform_summary(score_version=score_version, top_n=top_n)

    @app.get("/api/market-monitor/eod")
    def market_monitor_eod(
        trade_date: str | None = None,
        score_version: str = "manual_v1",
        top_n: int = 5,
    ):
        return build_market_monitor_eod(
            trade_date=trade_date,
            score_version=score_version,
            top_n=top_n,
        )

    @app.get("/api/public-news")
    def public_news(
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        asset_id: str | None = None,
        ts_code: str | None = None,
        min_quality_score: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return load_public_news_for_dashboard(
            source=source,
            category=category,
            q=q,
            start_time=start_time,
            end_time=end_time,
            asset_id=asset_id,
            ts_code=ts_code,
            min_quality_score=min_quality_score,
            limit=limit,
            offset=offset,
        )

    @app.post("/api/public-news/refresh")
    def public_news_refresh():
        return refresh_public_news_for_dashboard()

    @app.get("/api/public-news/status")
    def public_news_status():
        scheduler = getattr(app.state, "public_news_scheduler", None)
        if scheduler is None:
            return {
                "enabled": False,
                "running": False,
                "interval_seconds": NEWS_SCHEDULER_INTERVAL_SECONDS,
                "last_success_at": "",
                "last_error": "",
                "next_run_at": "",
            }
        return scheduler.status()

    @app.get("/api/search")
    def global_search(q: str, limit: int = 5):
        return load_global_search(q, limit=limit)

    @app.get("/api/research-reports/summary")
    def research_report_summary():
        return load_research_report_summary()

    @app.get("/api/research-reports")
    def research_reports(
        q: str | None = None,
        asset_id: str | None = None,
        ts_code: str | None = None,
        broker: str | None = None,
        rating: str | None = None,
        source_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        has_target_price: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return list_research_reports(
            q=q,
            asset_id=asset_id,
            ts_code=ts_code,
            broker=broker,
            rating=rating,
            source_name=source_name,
            start_date=start_date,
            end_date=end_date,
            has_target_price=has_target_price,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/assets/{asset_id}/research-reports")
    def asset_research_reports(asset_id: str, limit: int = 10, lookback_days: int = 90):
        return load_asset_research_reports(asset_id, limit=limit, lookback_days=lookback_days)

    @app.get("/api/assets/{asset_id}/news")
    def asset_news(
        asset_id: str,
        limit: int = 20,
        lookback_days: int = 7,
        category: str | None = None,
        source: str | None = None,
    ):
        return load_asset_news(
            asset_id,
            limit=limit,
            lookback_days=lookback_days,
            category=category,
            source=source,
        )

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

    @app.get("/api/assets/{asset_id}/profile")
    def asset_profile_route(
        asset_id: str,
        trade_date: str,
        start_date: str,
        end_date: str,
        score_version: str = "manual_v1",
        adjust_type: str = "qfq",
    ):
        return build_asset_profile(
            asset_id=asset_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            score_version=score_version,
            adjust_type=adjust_type,
        )

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

    @app.get("/api/outcome-analytics")
    def outcome_analytics(
        start_date: str,
        end_date: str,
        review_session_id: str | None = None,
        limit: int = 20,
    ):
        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": load_outcome_analytics_summary(
                start_date,
                end_date,
                review_session_id,
                limit,
            ),
        }

    @app.get("/api/experiment-proposals")
    def experiment_proposals(
        start_date: str,
        end_date: str,
        status: str | None = None,
        limit: int = 20,
    ):
        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": load_experiment_proposals_summary(
                start_date,
                end_date,
                status,
                limit,
            ),
        }

    @app.get("/api/experiment-replay")
    def experiment_replay(
        start_date: str,
        end_date: str,
        status: str | None = None,
        limit: int = 20,
    ):
        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": load_experiment_replay_summary(
                start_date,
                end_date,
                status,
                limit,
            ),
        }

    @app.get("/api/shadow-watchlist")
    def shadow_watchlist(
        start_date: str,
        end_date: str,
        status: str | None = None,
        limit: int = 20,
    ):
        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": load_shadow_watchlist_summary(
                start_date,
                end_date,
                status,
                limit,
            ),
        }

    @app.get("/api/shadow-outcomes")
    def shadow_outcomes(
        start_date: str,
        end_date: str,
        outcome_status: str | None = None,
        limit: int = 20,
    ):
        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": load_shadow_outcomes_summary(
                start_date,
                end_date,
                outcome_status,
                limit,
            ),
        }

    @app.get("/api/shadow-outcome-analytics")
    def shadow_outcome_analytics(
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "items": load_shadow_outcome_analytics_summary(
                start_date,
                end_date,
                limit,
            ),
        }

    @app.get("/api/shadow-analytics-review")
    def shadow_analytics_review(
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "items": load_shadow_analytics_review_summary(
                start_date,
                end_date,
                limit,
            ),
        }

    @app.get("/api/shadow-review-decisions")
    def shadow_review_decisions(
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "items": load_shadow_review_decision_summary(
                start_date,
                end_date,
                limit,
            ),
        }

    @app.get("/api/shadow-follow-up-queue")
    def shadow_follow_up_queue(
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "items": load_shadow_follow_up_queue_summary(
                start_date,
                end_date,
                limit,
            ),
        }

    @app.get("/api/shadow-follow-up-resolution")
    def shadow_follow_up_resolution(
        start_date: str,
        end_date: str,
        limit: int = 20,
    ):
        return {
            "items": load_shadow_follow_up_resolution_summary(
                start_date,
                end_date,
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

    @app.get("/api/strategies/catalog")
    def strategies_catalog():
        return {"items": list_strategy_catalog()}

    @app.get("/api/backtests/strategies")
    def backtest_strategies():
        return {"items": list_backtest_strategies()}

    @app.post("/api/backtests/run")
    def backtest_run(payload: dict):
        try:
            return run_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/backtests/run-fresh")
    def backtest_run_fresh(payload: dict):
        try:
            return run_fresh_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/backtests/run-replay")
    def backtest_run_replay(payload: dict):
        try:
            return run_replay_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/factors/library")
    def factor_library():
        return {"items": list_factor_library()}

    @app.get("/api/factors/score-preview")
    def factor_score_preview(trade_date: str, factors: str, top_n: int = 30):
        try:
            selected_factors = parse_factor_selection(factors)
            return build_factor_score_preview(
                trade_date=trade_date,
                selected_factors=selected_factors,
                top_n=top_n,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/strategy-validation/runs")
    def strategy_validation_runs(strategy_id: str | None = None):
        return {"items": list_strategy_validation_runs(strategy_id)}

    @app.get("/api/strategy-validation/runs/{run_id}")
    def strategy_validation_run(run_id: str):
        run = load_strategy_validation_run(run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail="strategy validation run not found",
            )
        return {"item": run}

    @app.get("/api/strategy-validation/runs/{run_id}/signals")
    def strategy_validation_signals(
        run_id: str,
        asset_id: str | None = None,
        signal_bucket: str | None = None,
        risk_bucket: str | None = None,
    ):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_signals(
                run_id,
                asset_id=asset_id,
                signal_bucket=signal_bucket,
                risk_bucket=risk_bucket,
            ),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/trades")
    def strategy_validation_trades(run_id: str, asset_id: str | None = None):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_trades(run_id, asset_id=asset_id),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/positions")
    def strategy_validation_positions(run_id: str, asset_id: str | None = None):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_positions(run_id, asset_id=asset_id),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/metrics")
    def strategy_validation_metrics(run_id: str, metric_level: str | None = None):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_metrics(
                run_id,
                metric_level=metric_level,
            ),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/artifacts")
    def strategy_validation_artifacts(run_id: str):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_artifacts(run_id),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/assets/{asset_id}/replay")
    def strategy_validation_asset_replay(
        run_id: str,
        asset_id: str,
        start_date: str,
        end_date: str,
        adjust_type: str = "qfq",
    ):
        bars = load_daily_bars(asset_id, start_date, end_date, adjust_type)
        return build_strategy_validation_replay(run_id, asset_id, bars)

    return app


app = create_app()
