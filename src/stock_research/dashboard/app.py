from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException

from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.backtests import (
    list_backtest_strategies,
    run_backtest,
    run_fresh_backtest,
    run_replay_backtest,
)
from stock_research.dashboard.backtest_jobs import BacktestJobStore
from stock_research.dashboard.bars import load_bars, load_daily_bars, load_minute_bars, normalize_resolution
from stock_research.dashboard.decisions import load_asset_decision_history, update_operator_decision_event
from stock_research.dashboard.evidence_digest import build_evidence_digest
from stock_research.dashboard.experiment_proposals import load_experiment_proposals_summary
from stock_research.dashboard.experiment_replay import load_experiment_replay_summary
from stock_research.dashboard.factors import (
    build_factor_score_preview,
    list_factor_library,
    parse_factor_selection,
)
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.market_overview_service import build_market_overview_payload
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
from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    load_ops_stage_details,
)
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.readiness import build_platform_readiness
from stock_research.dashboard.response_cache import DashboardResponseCache, dashboard_eod_cache_ttl_seconds
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import (
    list_research_reports,
    load_asset_research_reports,
    load_research_report_summary,
)
from stock_research.dashboard.review_queue import build_review_queue
from stock_research.review_evidence_snapshots import (
    list_evidence_digest_snapshots,
    list_review_item_snapshots,
    load_evidence_digest_snapshot,
)
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
    load_top_scores_for_dashboard,
    search_assets,
)
from stock_research.dashboard.search import load_global_search
from stock_research.dashboard.sector_detail_service import build_sector_detail_payload
from stock_research.dashboard.sector_fund_flow_service import build_sector_fund_flow_payload
from stock_research.dashboard.sector_heatmap_service import build_sector_heatmap_payload
from stock_research.dashboard.schemas import SectorType
from stock_research.dashboard.shadow_outcomes import load_shadow_outcomes_summary
from stock_research.dashboard.shadow_analytics_review import load_shadow_analytics_review_summary
from stock_research.dashboard.shadow_outcome_analytics import load_shadow_outcome_analytics_summary
from stock_research.dashboard.shadow_review_decisions import load_shadow_review_decision_summary
from stock_research.dashboard.shadow_follow_up_queue import load_shadow_follow_up_queue_summary
from stock_research.dashboard.shadow_follow_up_resolution import load_shadow_follow_up_resolution_summary
from stock_research.dashboard.shadow_watchlist import load_shadow_watchlist_summary
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.dashboard.strategy_score_audit import load_strategy_score_audit_payload
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
from stock_research.operator_decision.write_service import create_operator_decision

try:
    from stock_research.intraday_pipeline import IntradayConfig, parse_trade_date
except ModuleNotFoundError as exc:
    if exc.name != "stock_research.intraday_pipeline":
        raise

    class IntradayConfig:
        def __init__(self, timezone: str = "Asia/Shanghai"):
            self.timezone = timezone

        @classmethod
        def from_env(cls) -> "IntradayConfig":
            return cls()

    def parse_trade_date(value: str | date | None, timezone: str = "Asia/Shanghai") -> date:
        if isinstance(value, date):
            return value
        if value:
            normalized = value.replace("-", "")
            return datetime.strptime(normalized, "%Y%m%d").date()
        return datetime.now(ZoneInfo(timezone)).date()


def _resolve_dashboard_trade_date(raw_date: str | None):
    config = IntradayConfig.from_env()
    return parse_trade_date(raw_date, config.timezone)

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
    app.state.eod_response_cache = DashboardResponseCache(ttl_seconds=dashboard_eod_cache_ttl_seconds())
    app.state.backtest_jobs = BacktestJobStore(run_fresh_backtest)
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
        return app.state.eod_response_cache.get_or_set(
            ("platform_summary", score_version, top_n),
            lambda: load_platform_summary(score_version=score_version, top_n=top_n),
        )

    @app.get("/api/platform/readiness")
    def platform_readiness(score_version: str = "manual_v1"):
        return app.state.eod_response_cache.get_or_set(
            ("platform_readiness", score_version),
            lambda: build_platform_readiness(score_version=score_version),
        )

    @app.get("/api/platform/display-date")
    def platform_display_date(score_version: str = "manual_v1"):
        def build_payload():
            readiness = build_platform_readiness(score_version=score_version)
            display_gate = readiness.get("display_gate") if isinstance(readiness.get("display_gate"), dict) else {}
            if "display_trade_date" in readiness:
                display_trade_date = str(readiness.get("display_trade_date") or "")
            else:
                display_trade_date = str(
                    display_gate.get("display_trade_date")
                    or readiness.get("latest_trade_date")
                    or ""
                )
            candidate_trade_date = str(
                readiness.get("candidate_trade_date")
                or display_gate.get("candidate_trade_date")
                or readiness.get("latest_trade_date")
                or ""
            )
            return {
                "display_trade_date": display_trade_date,
                "candidate_trade_date": candidate_trade_date,
                "latest_market_date": str(readiness.get("latest_market_date") or ""),
                "status": readiness.get("status") or "",
                "display_gate": display_gate,
                "warnings": list(readiness.get("warnings") or []),
            }

        return app.state.eod_response_cache.get_or_set(
            ("platform_display_date", score_version),
            build_payload,
        )

    @app.get("/api/ops/snapshot")
    def ops_snapshot(date: str | None = None):
        return build_internal_ops_snapshot(trade_date=_resolve_dashboard_trade_date(date))

    @app.get("/api/ops/stages")
    def ops_stages(date: str | None = None):
        return {"items": load_ops_stage_details(trade_date=_resolve_dashboard_trade_date(date))}

    @app.get("/api/public/snapshot")
    def public_snapshot():
        return build_public_snapshot(trade_date=_resolve_dashboard_trade_date(None))

    @app.get("/api/market-monitor/eod")
    def market_monitor_eod(
        trade_date: str | None = None,
        score_version: str = "manual_v1",
        top_n: int = 5,
    ):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_eod", trade_date or "", score_version, top_n),
            lambda: build_market_monitor_eod(
                trade_date=trade_date,
                score_version=score_version,
                top_n=top_n,
            ),
        )

    @app.get("/api/market-monitor/overview")
    def market_monitor_overview(trade_date: str):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_overview", trade_date),
            lambda: build_market_overview_payload(trade_date),
        )

    @app.get("/api/market-monitor/sectors/heatmap")
    def market_monitor_sector_heatmap(trade_date: str, type: SectorType = "industry"):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_sector_heatmap", trade_date, type),
            lambda: build_sector_heatmap_payload(
                trade_date,
                sector_type=type,
            ),
        )

    @app.get("/api/market-monitor/sectors/fund-flow")
    def market_monitor_sector_fund_flow(
        trade_date: str,
        type: SectorType = "industry",
        period: str = "1d",
    ):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_sector_fund_flow", trade_date, type, period),
            lambda: build_sector_fund_flow_payload(
                trade_date,
                sector_type=type,
                period=period,
            ),
        )

    @app.get("/api/market-monitor/sectors/{sector_id}")
    def market_monitor_sector_detail(
        sector_id: str,
        trade_date: str,
        type: SectorType = "industry",
    ):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_sector_detail", trade_date, sector_id, type),
            lambda: build_sector_detail_payload(
                trade_date,
                sector_id,
                sector_type=type,
            ),
        )

    @app.get("/api/evidence-digest")
    def evidence_digest_route(
        asset_id: str,
        trade_date: str | None = None,
        lookback_days: int = 90,
        score_version: str = "manual_v1",
    ):
        return build_evidence_digest(
            asset_id,
            trade_date=trade_date,
            lookback_days=lookback_days,
            score_version=score_version,
        )

    @app.get("/api/strategy-score-audit")
    def strategy_score_audit_route(trade_date: str):
        return app.state.eod_response_cache.get_or_set(
            ("strategy_score_audit", trade_date),
            lambda: load_strategy_score_audit_payload(trade_date=trade_date),
        )

    @app.get("/api/review-queue")
    def review_queue_route(
        trade_date: str | None = None,
        score_version: str = "manual_v1",
        limit: int = 20,
        lookback_days: int = 90,
    ):
        return app.state.eod_response_cache.get_or_set(
            ("review_queue", trade_date or "", score_version, limit, lookback_days),
            lambda: build_review_queue(
                trade_date=trade_date,
                score_version=score_version,
                limit=limit,
                lookback_days=lookback_days,
            ),
        )

    @app.get("/api/review-queue/snapshots")
    def review_queue_snapshots(
        run_id: str | None = None,
        trade_date: str | None = None,
        asset_id: str | None = None,
        digest_key: str | None = None,
        limit: int = 100,
    ):
        return {
            "items": list_review_item_snapshots(
                run_id=run_id,
                trade_date=trade_date,
                asset_id=asset_id,
                digest_key=digest_key,
                limit=limit,
            ),
            "warnings": [],
            "as_of": "",
            "source": "ops.review_item_snapshot",
        }

    @app.get("/api/evidence-digest/snapshots")
    def evidence_digest_snapshots(
        run_id: str | None = None,
        trade_date: str | None = None,
        asset_id: str | None = None,
        digest_key: str | None = None,
        limit: int = 100,
    ):
        return {
            "items": list_evidence_digest_snapshots(
                run_id=run_id,
                trade_date=trade_date,
                asset_id=asset_id,
                digest_key=digest_key,
                limit=limit,
            ),
            "warnings": [],
            "as_of": "",
            "source": "ops.evidence_digest_snapshot",
        }

    @app.get("/api/evidence-digest/snapshots/{snapshot_id}")
    def evidence_digest_snapshot_detail(snapshot_id: str):
        item = load_evidence_digest_snapshot(snapshot_id)
        if item is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return {"item": item, "warnings": [], "source": "ops.evidence_digest_snapshot"}

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
        app.state.eod_response_cache.clear()
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
        end_date: str,
        start_date: str | None = None,
        resolution: str = "1D",
        adjust_type: str = "qfq",
        source: str = "baostock",
    ):
        resolved_resolution = normalize_resolution(resolution)
        return {
            "asset_id": asset_id,
            "resolution": resolved_resolution,
            "items": load_bars(
                asset_id=asset_id,
                end_date=end_date,
                start_date=start_date,
                resolution=resolved_resolution,
                adjust_type=adjust_type,
                source=source,
            ),
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

    @app.post("/api/operator-decisions")
    def operator_decisions(payload: dict):
        try:
            return create_operator_decision(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/operator-decisions/{event_id}")
    def operator_decision_update(event_id: str, payload: dict):
        try:
            return {"item": update_operator_decision_event(event_id, payload)}
        except ValueError as exc:
            status_code = 404 if str(exc) == "decision_event_not_found" else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

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

    @app.post("/api/backtests/jobs")
    def backtest_job_submit(payload: dict):
        try:
            return app.state.backtest_jobs.submit(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/backtests/jobs/{job_id}")
    def backtest_job_status(job_id: str):
        try:
            return app.state.backtest_jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="backtest job not found") from exc

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
