from contextlib import asynccontextmanager
from datetime import date, datetime
from inspect import signature
import os
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from stock_research.config import SETTINGS
from stock_research.dashboard.api_guardrails import (
    PublicationGuardBlocked,
    assert_publication_ready,
    require_guarded_operation,
)
from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.auth_service import (
    authenticate_user,
    create_session,
    current_user_read_model,
    load_current_user_from_session,
    revoke_session,
    validate_csrf,
)
from stock_research.dashboard.backtests import (
    list_backtest_strategies,
    run_backtest,
    run_fresh_backtest,
    run_replay_backtest,
)
from stock_research.dashboard.backtest_jobs import BacktestJobStore
from stock_research.dashboard.bars import load_bars, load_daily_bars, load_minute_bars, normalize_resolution
from stock_research.dashboard.decisions import (
    load_asset_decision_history,
    update_operator_decision_event,
    validate_operator_decision_payload as validate_structured_operator_decision_payload,
)
from stock_research.dashboard.daily_review_lite import build_daily_review_lite
from stock_research.dashboard.evidence_digest import build_evidence_digest
from stock_research.dashboard.evidence_registry import evidence_artifact_read_model, list_evidence_artifacts
from stock_research.dashboard.experiment_proposals import load_experiment_proposals_summary
from stock_research.dashboard.experiment_replay import load_experiment_replay_summary
from stock_research.dashboard.factors import (
    build_factor_score_preview,
    list_factor_library,
    parse_factor_selection,
)
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.market_overview_service import build_market_overview_payload
from stock_research.dashboard.market_anomaly_context import (
    build_market_anomaly_context,
    market_anomaly_context_read_model,
)
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
from stock_research.dashboard.operator_decision_validation import validate_operator_decision_payload
from stock_research.dashboard.overview import build_dashboard_overview
from stock_research.dashboard.observability import install_request_id_middleware
from stock_research.dashboard.outcome_analytics import load_outcome_analytics_summary
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    load_ops_stage_details,
)
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.readiness import build_platform_readiness
from stock_research.dashboard.read_models import platform_summary_read_model
from stock_research.dashboard.response_cache import DashboardResponseCache, dashboard_eod_cache_ttl_seconds
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_cases import (
    list_research_cases,
    load_research_case_detail,
    research_case_detail_read_model,
    research_case_read_model,
)
from stock_research.dashboard.research_queue_health import (
    load_research_queue_health,
    research_queue_health_read_model,
)
from stock_research.dashboard.research_queue_gaps import list_research_queue_gaps, research_queue_gaps_read_model
from stock_research.dashboard.research_publish_gate import get_research_publish_gate, research_publish_gate_read_model
from stock_research.dashboard.research_publication_snapshots import (
    get_publication_snapshot,
    list_publication_snapshots,
)
from stock_research.dashboard.research_reports import (
    list_research_reports,
    load_asset_research_reports,
    load_research_report_document,
    load_research_report_pdf_path,
    load_research_report_summary,
)
from stock_research.dashboard.review_queue import build_review_queue
from stock_research.review_evidence_snapshots import (
    list_evidence_digest_snapshots,
    list_review_item_snapshots,
    load_evidence_digest_snapshot,
)
from stock_research.research_review_actions import (
    list_review_actions,
    record_review_action,
    review_action_read_model,
)
from stock_research.research_publication_package import (
    build_research_publication_package,
    research_publication_package_read_model,
)
from stock_research.research_external_delivery import (
    build_research_external_delivery_plan,
    delivery_plan_read_model,
)
from stock_research.research_external_delivery_attempts import (
    get_external_delivery_attempt,
    list_external_delivery_attempts,
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
from stock_research.dashboard.stock_heatmap_service import (
    build_stock_heatmap_payload,
    stock_heatmap_read_model,
)
from stock_research.dashboard.stock_market_context_heatmap import (
    build_stock_market_context_heatmap,
    stock_market_context_heatmap_read_model,
)
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
from stock_research.dashboard.tech_bottleneck_review_universe import (
    get_review_universe_stock,
    list_review_universe_evidence,
    list_review_universe_sources,
    list_review_universe_stocks,
    load_review_universe_filter_options,
    load_review_universe_summary,
)
from stock_research.dashboard.tech_bottleneck_review_decisions import (
    build_decision_summary as build_tech_bottleneck_review_decision_summary,
    list_manual_decisions as list_tech_bottleneck_review_decisions,
    record_manual_decision as record_tech_bottleneck_review_decision,
)
from stock_research.dashboard.theme_research import (
    ThemeResearchNotFoundError,
    get_theme_research_theme,
    list_theme_research_claims,
    list_theme_research_companies,
    list_theme_research_nodes,
    list_theme_research_sources,
    list_theme_research_themes,
)
from stock_research.dashboard.theme_research_context import load_asset_theme_context
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_store import (
    list_review_history as list_theme_research_review_history,
    list_snapshots as list_theme_research_snapshots,
    review_claim as review_theme_research_claim,
    review_node as review_theme_research_node,
    review_source as review_theme_research_source,
    rollback_theme as rollback_theme_research_theme,
)
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
from stock_research.dashboard.user_admin import (
    create_dashboard_user,
    list_admin_users,
    reset_dashboard_user_password,
    set_dashboard_user_active,
)
from stock_research.data_to_brief_docling_90_stock_review_dashboard_integration import (
    load_dashboard_payload as load_data_to_brief_docling_90_dashboard_payload,
)
from stock_research.daily_close_pipeline import load_data_status_for_dashboard
from stock_research.operator_decision.write_service import create_operator_decision

try:
    from stock_research.intraday_pipeline import IntradayConfig, load_intraday_status, parse_trade_date
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


def _resolve_ops_snapshot_route_trade_date(raw_date: str | None):
    if raw_date:
        return _resolve_dashboard_trade_date(raw_date)
    if "service" not in signature(build_internal_ops_snapshot).parameters:
        return None
    return _resolve_dashboard_trade_date(raw_date)


def load_midtrend_post_exit_review_lite() -> dict:
    return {
        "schema_version": "midtrend_post_exit_watch_daily_review_lite_v1",
        "sections": {},
        "artifact_health": {"exists": False, "warning": "artifact_missing"},
    }


def _require_guard(request: Request, operation: str) -> None:
    try:
        require_guarded_operation(operation=operation, headers=request.headers)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


class LoginPayload(BaseModel):
    username: str
    password: str


class AdminCreateUserPayload(BaseModel):
    username: str
    password: str
    role: str = "user"
    display_name: str = ""


class AdminResetPasswordPayload(BaseModel):
    password: str


class ThemeResearchReviewRequest(BaseModel):
    to_status: str
    expected_row_version: int
    comment: str
    idempotency_key: str


class ThemeResearchRollbackRequest(BaseModel):
    snapshot_id: str
    expected_theme_version: int
    comment: str
    idempotency_key: str


def _set_auth_cookies(response: JSONResponse, session_token: str, csrf_token: str) -> None:
    response.set_cookie(
        SETTINGS.dashboard_session_cookie,
        session_token,
        httponly=True,
        secure=SETTINGS.dashboard_cookie_secure,
        samesite="lax",
        max_age=SETTINGS.dashboard_session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        SETTINGS.dashboard_csrf_cookie,
        csrf_token,
        httponly=False,
        secure=SETTINGS.dashboard_cookie_secure,
        samesite="lax",
        max_age=SETTINGS.dashboard_session_ttl_seconds,
        path="/",
    )


def _current_user_or_401(request: Request):
    session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
    user = load_current_user_from_session(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user


def _admin_user_or_403(request: Request):
    user = _current_user_or_401(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    return user


def _require_csrf(request: Request) -> None:
    try:
        validate_csrf(
            csrf_cookie=request.cookies.get(SETTINGS.dashboard_csrf_cookie, ""),
            csrf_header=str(request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token") or ""),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _theme_research_http_error(exc: ThemeResearchDomainError) -> HTTPException:
    if exc.code == "THEME_RESEARCH_VERSION_CONFLICT":
        status_code = 409
    elif exc.code in {"THEME_RESEARCH_ADMIN_REQUIRED", "THEME_RESEARCH_REVIEW_ROLE_INVALID"}:
        status_code = 403
    elif exc.code in {"THEME_RESEARCH_OBJECT_NOT_FOUND", "THEME_RESEARCH_THEME_NOT_FOUND"}:
        status_code = 404
    else:
        status_code = 400
    return HTTPException(
        status_code=status_code,
        detail={
            "status": "error",
            "error_code": exc.code,
            "message": str(exc),
            "details": exc.details,
        },
    )


AUTH_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}


def _dashboard_auth_required() -> bool:
    raw = os.environ.get("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return SETTINGS.dashboard_auth_required


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
    install_request_id_middleware(app)
    app.state.eod_response_cache = DashboardResponseCache(ttl_seconds=dashboard_eod_cache_ttl_seconds())
    app.state.backtest_jobs = BacktestJobStore(run_fresh_backtest)
    app.state.public_news_scheduler = PublicNewsScheduler(
        refresh_public_news_for_dashboard,
        interval_seconds=NEWS_SCHEDULER_INTERVAL_SECONDS,
        enabled=scheduler_enabled_from_env(),
    )

    @app.middleware("http")
    async def dashboard_auth_required_middleware(request: Request, call_next):
        if (
            _dashboard_auth_required()
            and request.url.path.startswith("/api/")
            and request.url.path not in AUTH_EXEMPT_PATHS
        ):
            session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
            if load_current_user_from_session(session_token) is None:
                return JSONResponse({"detail": "not_authenticated"}, status_code=401)
        return await call_next(request)

    @app.get("/api/auth/me")
    def auth_me(request: Request):
        session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
        user = load_current_user_from_session(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="not_authenticated")
        return {"user": current_user_read_model(user)}

    @app.post("/api/auth/login")
    def auth_login(payload: LoginPayload, request: Request):
        try:
            user = authenticate_user(payload.username, payload.password)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        session = create_session(
            user,
            user_agent=str(request.headers.get("user-agent") or ""),
            ip_address=str(request.client.host if request.client else ""),
        )
        response = JSONResponse({"user": current_user_read_model(user)})
        _set_auth_cookies(response, str(session["session_token"]), str(session["csrf_token"]))
        return response

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
        if session_token:
            revoke_session(session_token)
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie(SETTINGS.dashboard_session_cookie, path="/")
        response.delete_cookie(SETTINGS.dashboard_csrf_cookie, path="/")
        return response

    @app.get("/api/admin/users")
    def admin_users(request: Request):
        _admin_user_or_403(request)
        return {"items": list_admin_users()}

    @app.post("/api/admin/users")
    def admin_create_user(payload: AdminCreateUserPayload, request: Request):
        _admin_user_or_403(request)
        _require_csrf(request)
        try:
            user = create_dashboard_user(
                payload.username,
                payload.password,
                role=payload.role,
                display_name=payload.display_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"user": user}

    @app.post("/api/admin/users/{user_id}/disable")
    def admin_disable_user(user_id: str, request: Request):
        _admin_user_or_403(request)
        _require_csrf(request)
        set_dashboard_user_active(user_id, False)
        return {"status": "disabled", "user_id": user_id}

    @app.post("/api/admin/users/{user_id}/enable")
    def admin_enable_user(user_id: str, request: Request):
        _admin_user_or_403(request)
        _require_csrf(request)
        set_dashboard_user_active(user_id, True)
        return {"status": "enabled", "user_id": user_id}

    @app.post("/api/admin/users/{user_id}/reset-password")
    def admin_reset_password(user_id: str, payload: AdminResetPasswordPayload, request: Request):
        _admin_user_or_403(request)
        _require_csrf(request)
        reset_dashboard_user_password(user_id, payload.password)
        return {"status": "password_reset", "user_id": user_id}

    @app.get("/api/dashboard/overview")
    def dashboard_overview(
        trade_date: str,
        score_version: str = "manual_v1",
        watchlist_id: str = "default",
        top_n: int = 10,
    ):
        return build_dashboard_overview(trade_date, score_version, watchlist_id, top_n)

    @app.get("/api/platform/summary")
    def platform_summary(score_version: str = "manual_v1", top_n: int = 5):
        return app.state.eod_response_cache.get_or_set(
            ("platform_summary", score_version, top_n),
            lambda: platform_summary_read_model(load_platform_summary(score_version=score_version, top_n=top_n)),
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

    @app.get("/api/data/status")
    def data_status():
        return load_data_status_for_dashboard()

    @app.get("/api/research/data-to-brief/docling-90")
    def data_to_brief_docling_90_review():
        return load_data_to_brief_docling_90_dashboard_payload()

    @app.get("/api/research/theme-decomposition/themes")
    def theme_research_themes():
        return list_theme_research_themes()

    @app.get("/api/research/theme-decomposition/themes/{theme_id}")
    def theme_research_theme_detail(theme_id: str):
        try:
            return get_theme_research_theme(theme_id)
        except ThemeResearchNotFoundError as exc:
            raise HTTPException(status_code=404, detail="theme_not_found") from exc

    @app.get("/api/research/theme-decomposition/themes/{theme_id}/nodes")
    def theme_research_theme_nodes(theme_id: str):
        try:
            return list_theme_research_nodes(theme_id)
        except ThemeResearchNotFoundError as exc:
            raise HTTPException(status_code=404, detail="theme_not_found") from exc

    @app.get("/api/research/theme-decomposition/themes/{theme_id}/sources")
    def theme_research_theme_sources(theme_id: str):
        try:
            return list_theme_research_sources(theme_id)
        except ThemeResearchNotFoundError as exc:
            raise HTTPException(status_code=404, detail="theme_not_found") from exc

    @app.get("/api/research/theme-decomposition/themes/{theme_id}/claims")
    def theme_research_theme_claims(theme_id: str):
        try:
            return list_theme_research_claims(theme_id)
        except ThemeResearchNotFoundError as exc:
            raise HTTPException(status_code=404, detail="theme_not_found") from exc

    @app.get("/api/research/theme-decomposition/themes/{theme_id}/companies")
    def theme_research_theme_companies(theme_id: str):
        try:
            return list_theme_research_companies(theme_id)
        except ThemeResearchNotFoundError as exc:
            raise HTTPException(status_code=404, detail="theme_not_found") from exc

    @app.get("/api/assets/{asset_id}/theme-research-context")
    def asset_theme_research_context(asset_id: str):
        return load_asset_theme_context(asset_id)

    @app.post("/api/research/theme-decomposition/sources/{source_id}/review")
    def theme_research_review_source(
        source_id: str,
        payload: ThemeResearchReviewRequest,
        request: Request,
    ):
        user = _current_user_or_401(request)
        _require_csrf(request)
        try:
            return review_theme_research_source(
                source_id=source_id,
                to_status=payload.to_status,
                expected_row_version=payload.expected_row_version,
                actor_user_id=user.user_id,
                actor_role=user.role,
                comment=payload.comment,
                request_id=str(request.state.request_id),
                idempotency_key=payload.idempotency_key,
            )
        except ThemeResearchDomainError as exc:
            raise _theme_research_http_error(exc) from exc

    @app.post("/api/research/theme-decomposition/claims/{claim_id}/review")
    def theme_research_review_claim(
        claim_id: str,
        payload: ThemeResearchReviewRequest,
        request: Request,
    ):
        user = _current_user_or_401(request)
        _require_csrf(request)
        try:
            return review_theme_research_claim(
                claim_id=claim_id,
                to_status=payload.to_status,
                expected_row_version=payload.expected_row_version,
                actor_user_id=user.user_id,
                actor_role=user.role,
                comment=payload.comment,
                request_id=str(request.state.request_id),
                idempotency_key=payload.idempotency_key,
            )
        except ThemeResearchDomainError as exc:
            raise _theme_research_http_error(exc) from exc

    @app.post("/api/research/theme-decomposition/nodes/{node_id}/review")
    def theme_research_review_node(
        node_id: str,
        payload: ThemeResearchReviewRequest,
        request: Request,
    ):
        user = _current_user_or_401(request)
        _require_csrf(request)
        try:
            return review_theme_research_node(
                node_id=node_id,
                to_status=payload.to_status,
                expected_row_version=payload.expected_row_version,
                actor_user_id=user.user_id,
                actor_role=user.role,
                comment=payload.comment,
                request_id=str(request.state.request_id),
                idempotency_key=payload.idempotency_key,
            )
        except ThemeResearchDomainError as exc:
            raise _theme_research_http_error(exc) from exc

    @app.get("/api/research/theme-decomposition/history")
    def theme_research_review_history(
        request: Request,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
    ):
        _current_user_or_401(request)
        return list_theme_research_review_history(
            object_type=object_type,
            object_id=object_id,
            limit=limit,
        )

    @app.get("/api/research/theme-decomposition/themes/{theme_id}/snapshots")
    def theme_research_snapshots(theme_id: str, request: Request, limit: int = 100):
        _current_user_or_401(request)
        return list_theme_research_snapshots(theme_id=theme_id, limit=limit)

    @app.post("/api/research/theme-decomposition/themes/{theme_id}/rollback")
    def theme_research_rollback(
        theme_id: str,
        payload: ThemeResearchRollbackRequest,
        request: Request,
    ):
        user = _admin_user_or_403(request)
        _require_csrf(request)
        try:
            return rollback_theme_research_theme(
                theme_id=theme_id,
                snapshot_id=payload.snapshot_id,
                expected_theme_version=payload.expected_theme_version,
                actor_user_id=user.user_id,
                actor_role=user.role,
                comment=payload.comment,
                idempotency_key=payload.idempotency_key,
                request_id=str(request.state.request_id),
            )
        except ThemeResearchDomainError as exc:
            raise _theme_research_http_error(exc) from exc

    @app.get("/api/research/tech-bottleneck/review-universe/summary")
    def tech_bottleneck_review_universe_summary():
        return load_review_universe_summary()

    @app.get("/api/research/tech-bottleneck/review-universe/stocks")
    def tech_bottleneck_review_universe_stocks(
        review_universe_source: str | None = None,
        current_layer_status: str | None = None,
        manual_approval_status: str | None = None,
        hard_tech_domain: str | None = None,
        supply_chain_role_hint: str | None = None,
        concept_pollution_risk: str | None = None,
        route_around_or_substitution_risk: str | None = None,
        value_capture_risk: str | None = None,
        primary_source_supported: str | None = None,
        frontend_review_status: str | None = None,
        reviewer_decision: str | None = None,
        quality_reassessment_tier: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return list_review_universe_stocks(
            review_universe_source=review_universe_source,
            current_layer_status=current_layer_status,
            manual_approval_status=manual_approval_status,
            hard_tech_domain=hard_tech_domain,
            supply_chain_role_hint=supply_chain_role_hint,
            concept_pollution_risk=concept_pollution_risk,
            route_around_or_substitution_risk=route_around_or_substitution_risk,
            value_capture_risk=value_capture_risk,
            primary_source_supported=primary_source_supported,
            frontend_review_status=frontend_review_status,
            reviewer_decision=reviewer_decision,
            quality_reassessment_tier=quality_reassessment_tier,
            q=q,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/research/tech-bottleneck/review-universe/stocks/{stock_code}/evidence")
    def tech_bottleneck_review_universe_stock_evidence(stock_code: str):
        return list_review_universe_evidence(stock_code)

    @app.get("/api/research/tech-bottleneck/review-universe/stocks/{stock_code}/sources")
    def tech_bottleneck_review_universe_stock_sources(stock_code: str):
        return list_review_universe_sources(stock_code)

    @app.get("/api/research/tech-bottleneck/review-universe/stocks/{stock_code}")
    def tech_bottleneck_review_universe_stock_detail(stock_code: str):
        stock = get_review_universe_stock(stock_code)
        if stock is None:
            raise HTTPException(status_code=404, detail="stock_not_found")
        return stock

    @app.get("/api/research/tech-bottleneck/review-universe/filter-options")
    def tech_bottleneck_review_universe_filter_options():
        return load_review_universe_filter_options()

    @app.post("/api/research/tech-bottleneck/review-universe/decisions")
    def tech_bottleneck_review_universe_decision_create(request: Request, payload: dict):
        try:
            _require_guard(request, "tech_bottleneck_review_decision_write")
            return record_tech_bottleneck_review_decision(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/research/tech-bottleneck/review-universe/decisions")
    def tech_bottleneck_review_universe_decisions(stock_code: str | None = None, limit: int = 50):
        return list_tech_bottleneck_review_decisions(stock_code=stock_code, limit=limit)

    @app.get("/api/research/tech-bottleneck/review-universe/decision-summary")
    def tech_bottleneck_review_universe_decision_summary():
        return build_tech_bottleneck_review_decision_summary()

    @app.get("/api/ops/snapshot")
    def ops_snapshot(date: str | None = None):
        return build_internal_ops_snapshot(
            trade_date=_resolve_ops_snapshot_route_trade_date(date)
        )

    @app.get("/api/ops/stages")
    def ops_stages(date: str | None = None):
        return {"items": load_ops_stage_details(trade_date=_resolve_dashboard_trade_date(date))}

    @app.get("/api/public/snapshot")
    def public_snapshot():
        return build_public_snapshot()

    @app.get("/api/intraday/status")
    def intraday_status(date: str | None = None):
        config = IntradayConfig.from_env()
        run_date = parse_trade_date(date, config.timezone)
        return load_intraday_status(config.service, run_date)

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

    @app.get("/api/market-monitor/stocks/heatmap")
    def market_monitor_stock_heatmap(
        trade_date: str,
        market: str = "all",
        period: str = "1d",
        group: str = "industry",
        size_by: str = "amount",
    ):
        try:
            return app.state.eod_response_cache.get_or_set(
                ("market_monitor_stock_heatmap", trade_date, market, period, group, size_by),
                lambda: stock_heatmap_read_model(
                    build_stock_heatmap_payload(
                        trade_date,
                        market=market,
                        period=period,
                        group=group,
                        size_by=size_by,
                    )
                ),
            )
        except ValueError as exc:
            if str(exc) == "unsupported_stock_heatmap_option":
                raise HTTPException(status_code=400, detail="unsupported_stock_heatmap_option") from exc
            raise

    @app.get("/api/market-monitor/anomaly-context")
    def market_monitor_anomaly_context(trade_date: str):
        return app.state.eod_response_cache.get_or_set(
            ("market_monitor_anomaly_context", trade_date),
            lambda: market_anomaly_context_read_model(build_market_anomaly_context(trade_date)),
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

    @app.get("/api/research/cases")
    def research_cases_route(
        trade_date: str | None = None,
        status: str | None = None,
        asset_id: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": [
                research_case_read_model(item)
                for item in list_research_cases(
                    trade_date=trade_date,
                    status=status,
                    asset_id=asset_id,
                    limit=limit,
                )
            ]
        }

    @app.get("/api/research/queue/health")
    def research_queue_health_route(trade_date: str | None = None):
        return research_queue_health_read_model(load_research_queue_health(trade_date=trade_date))

    @app.get("/api/research/queue/gaps")
    def research_queue_gaps_route(trade_date: str | None = None, limit: int = 50):
        return research_queue_gaps_read_model(list_research_queue_gaps(trade_date=trade_date, limit=limit))

    @app.get("/api/research/queue/publish-gate")
    def research_publish_gate_route(trade_date: str):
        return research_publish_gate_read_model(get_research_publish_gate(trade_date=trade_date))

    @app.get("/api/research/publication/preview")
    def research_publication_preview_route(trade_date: str):
        return research_publication_package_read_model(build_research_publication_package(trade_date=trade_date))

    @app.get("/api/research/publication/snapshots")
    def research_publication_snapshots_route(
        trade_date: str | None = None,
        channel: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": list_publication_snapshots(
                trade_date=trade_date,
                channel=channel,
                limit=limit,
            )
        }

    @app.get("/api/research/publication/snapshots/{publication_snapshot_id:path}")
    def research_publication_snapshot_detail_route(publication_snapshot_id: str):
        snapshot = get_publication_snapshot(publication_snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="publication_snapshot_not_found")
        return snapshot

    @app.get("/api/research/publication/delivery-plan")
    def research_external_delivery_plan_route(publication_snapshot_id: str, channel: str = "feishu_preview"):
        plan = build_research_external_delivery_plan(
            publication_snapshot_id=publication_snapshot_id,
            channel=channel,
        )
        if plan["status"] == "snapshot_not_found":
            raise HTTPException(status_code=404, detail="publication_snapshot_not_found")
        if plan["status"] == "unsupported_channel":
            raise HTTPException(status_code=400, detail="unsupported_delivery_channel")
        return delivery_plan_read_model(plan)

    @app.get("/api/research/publication/delivery-attempts")
    def research_external_delivery_attempts_route(
        publication_snapshot_id: str | None = None,
        trade_date: str | None = None,
        channel: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": list_external_delivery_attempts(
                publication_snapshot_id=publication_snapshot_id,
                trade_date=trade_date,
                channel=channel,
                limit=limit,
            )
        }

    @app.get("/api/research/publication/delivery-attempts/{delivery_attempt_id:path}")
    def research_external_delivery_attempt_detail_route(delivery_attempt_id: str):
        attempt = get_external_delivery_attempt(delivery_attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="delivery_attempt_not_found")
        return attempt

    @app.post("/api/research/review-actions")
    def research_review_action_create(request: Request, payload: dict):
        try:
            _require_guard(request, "research_review_action_write")
            review_action_id = record_review_action(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"review_action_id": review_action_id, "status": "recorded"}

    @app.get("/api/research/review-actions")
    def research_review_actions_route(
        case_id: str | None = None,
        trade_date: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": [
                item
                for item in (
                    review_action_read_model(action)
                    for action in list_review_actions(case_id=case_id, trade_date=trade_date, limit=limit)
                )
                if item is not None
            ]
        }

    @app.get("/api/research/cases/{case_id:path}")
    def research_case_detail_route(case_id: str, limit: int = 100):
        detail = load_research_case_detail(case_id, limit=limit)
        if detail is None:
            raise HTTPException(status_code=404, detail="research_case_not_found")
        return research_case_detail_read_model(detail)

    @app.get("/api/research/evidence")
    def research_evidence_route(
        asset_id: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": [
                evidence_artifact_read_model(item)
                for item in list_evidence_artifacts(
                    asset_id=asset_id,
                    source_type=source_type,
                    limit=limit,
                )
            ]
        }

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

    @app.get("/api/daily-review-lite")
    def daily_review_lite_route(trade_date: str | None = None):
        return app.state.eod_response_cache.get_or_set(
            ("daily_review_lite", trade_date or ""),
            lambda: build_daily_review_lite(trade_date=trade_date),
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
        filters = {
            "source": source,
            "category": category,
            "q": q,
            "limit": limit,
            "offset": offset,
        }
        optional_filters = {
            "start_time": start_time,
            "end_time": end_time,
            "asset_id": asset_id,
            "ts_code": ts_code,
            "min_quality_score": min_quality_score,
        }
        filters.update({key: value for key, value in optional_filters.items() if value is not None})
        return load_public_news_for_dashboard(**filters)

    @app.post("/api/public-news/refresh")
    def public_news_refresh(request: Request):
        _require_guard(request, "public_news_refresh")
        app.state.eod_response_cache.clear()
        return refresh_public_news_for_dashboard()

    @app.post("/api/dashboard/cache/clear")
    def dashboard_cache_clear(request: Request):
        _require_guard(request, "dashboard_cache_clear")
        app.state.eod_response_cache.clear()
        return {"status": "cleared"}

    @app.get("/api/midtrend/post-exit-review-lite")
    def midtrend_post_exit_review_lite():
        return load_midtrend_post_exit_review_lite()

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

    @app.get("/api/research-reports/{report_id}/document")
    def research_report_document(report_id: str):
        payload = load_research_report_document(report_id)
        if payload.get("warnings") == ["research report not found"]:
            raise HTTPException(status_code=404, detail="research report not found")
        return payload

    @app.get("/api/research-reports/{report_id}/pdf")
    def research_report_pdf(report_id: str):
        pdf_path = load_research_report_pdf_path(report_id)
        if not pdf_path:
            raise HTTPException(status_code=404, detail="research report pdf not found")
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=pdf_path.name,
            content_disposition_type="inline",
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

    @app.get("/api/stocks/{asset_id:path}/market-context/heatmap")
    def stock_market_context_heatmap(asset_id: str, trade_date: str):
        return app.state.eod_response_cache.get_or_set(
            ("stock_market_context_heatmap", asset_id, trade_date),
            lambda: stock_market_context_heatmap_read_model(
                build_stock_market_context_heatmap(asset_id, trade_date)
            ),
        )

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
    def operator_decisions(request: Request, payload: dict):
        try:
            _require_guard(request, "operator_decision_write")
            assert_publication_ready(lambda: build_platform_readiness(score_version="manual_v1"))
            validate_operator_decision_payload(payload)
            payload = validate_structured_operator_decision_payload(payload)
            return create_operator_decision(payload)
        except PublicationGuardBlocked as exc:
            raise HTTPException(status_code=409, detail=exc.detail) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/operator-decisions/{event_id}")
    def operator_decision_update(event_id: str, request: Request, payload: dict):
        try:
            _require_guard(request, "operator_decision_update")
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
    def topn(trade_date: str, score_version: str = "manual_v1", top_n: int = 10):
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
    def backtest_job_submit(request: Request, payload: dict):
        try:
            _require_guard(request, "backtest_job_submit")
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
    def backtest_run(request: Request, payload: dict):
        try:
            _require_guard(request, "backtest_run")
            return run_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/backtests/run-fresh")
    def backtest_run_fresh(request: Request, payload: dict):
        try:
            _require_guard(request, "backtest_run_fresh")
            return run_fresh_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/backtests/run-replay")
    def backtest_run_replay(request: Request, payload: dict):
        try:
            _require_guard(request, "backtest_run_replay")
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
