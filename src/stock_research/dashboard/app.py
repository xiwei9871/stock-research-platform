from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from psycopg import errors as psycopg_errors
from pydantic import BaseModel, Field, StringConstraints, field_validator

from stock_research.dashboard.audit import record_audit_log
from stock_research.dashboard.auth import (
    LOGIN_FAILURE_LIMIT,
    attach_auth_cookies,
    authenticate_dashboard_user,
    clear_auth_cookies,
    count_recent_login_failures,
    create_user_session,
    require_csrf,
    require_admin_user,
    require_current_user,
    revoke_user_session,
)
from stock_research.dashboard.bars import load_bars, load_minute_bars, normalize_resolution
from stock_research.dashboard.decisions import load_asset_decision_history
from stock_research.dashboard.experiment_proposals import load_experiment_proposals_summary
from stock_research.dashboard.experiment_replay import load_experiment_replay_summary
from stock_research.dashboard.overview import build_dashboard_overview
from stock_research.dashboard.outcome_analytics import load_outcome_analytics_summary
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
    load_top_scores_for_dashboard,
    search_assets,
)
from stock_research.dashboard.shadow_outcomes import load_shadow_outcomes_summary
from stock_research.dashboard.shadow_analytics_review import load_shadow_analytics_review_summary
from stock_research.dashboard.shadow_outcome_analytics import load_shadow_outcome_analytics_summary
from stock_research.dashboard.shadow_review_decisions import load_shadow_review_decision_summary
from stock_research.dashboard.shadow_follow_up_queue import load_shadow_follow_up_queue_summary
from stock_research.dashboard.shadow_follow_up_resolution import load_shadow_follow_up_resolution_summary
from stock_research.dashboard.shadow_watchlist import load_shadow_watchlist_summary
from stock_research.dashboard.watchlist import (
    load_asset_watchlist_signals_for_dashboard,
    load_watchlist_signals_for_dashboard,
)
from stock_research.dashboard.user_models import CurrentUser
from stock_research.dashboard.user_admin import (
    create_user_account,
    disable_user_account,
    enable_user_account,
    list_user_accounts,
    reset_user_password,
)
from stock_research.dashboard.user_watchlist import (
    create_user_watchlist_item,
    list_user_watchlist_items,
    soft_delete_user_watchlist_item,
    update_user_watchlist_item,
)
from stock_research.dashboard.user_reviews import (
    create_user_review_item,
    create_user_review_session,
    get_user_review_session,
    list_user_review_sessions,
    soft_delete_user_review_item,
    soft_delete_user_review_session,
    update_user_review_session,
    update_user_review_item,
)
from stock_research.dashboard.user_schema import apply_user_platform_schema
from stock_research.daily_close_pipeline import load_data_status_for_dashboard
from stock_research.intraday_pipeline import (
    IntradayConfig,
    load_intraday_status,
    parse_trade_date,
)
from stock_research.public_news.service import (
    load_public_news_for_dashboard,
    refresh_public_news_for_dashboard,
)


class LoginPayload(BaseModel):
    identifier: str
    password: str


class AdminCreateUserPayload(BaseModel):
    username: str
    email: str | None = None
    display_name: str
    password: str
    role: Literal["admin", "user"]

    @field_validator("username", "display_name")
    @classmethod
    def validate_non_blank_identity_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("password")
    @classmethod
    def validate_non_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ResetPasswordPayload(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_non_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class WatchlistItemPayload(BaseModel):
    asset_id: str
    source: str = "manual"
    notes: str = ""


class WatchlistItemUpdatePayload(BaseModel):
    source: str | None = None
    notes: str | None = None


NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReviewItemPayload(BaseModel):
    asset_id: NonBlankText
    decision: NonBlankText
    conviction: NonBlankText
    tags: list[str] | None = None
    notes: str | None = None
    follow_up_required: bool | None = None


class ReviewItemPatchPayload(BaseModel):
    tags: list[str] | None = None
    notes: str | None = None
    follow_up_required: bool | None = None
    decision: NonBlankText | None = None
    conviction: NonBlankText | None = None


class ReviewSessionPayload(BaseModel):
    trade_date: str
    title: str
    summary: str = ""
    market_view: str = ""
    position_view: str = ""
    next_action: str = ""
    items: list[ReviewItemPayload] = Field(default_factory=list)


class ReviewSessionPatchPayload(BaseModel):
    trade_date: str | None = None
    title: str | None = None
    summary: str | None = None
    market_view: str | None = None
    position_view: str | None = None
    next_action: str | None = None


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        apply_user_platform_schema()
        yield

    app = FastAPI(title="Stock Research Dashboard API", lifespan=lifespan)

    @app.post("/api/auth/login")
    def login(payload: LoginPayload, request: Request, response: Response):
        ip_address = request.client.host if request.client is not None else None
        if (
            count_recent_login_failures(identifier=payload.identifier, ip_address=ip_address)
            >= LOGIN_FAILURE_LIMIT
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many login attempts",
            )
        current_user = authenticate_dashboard_user(payload.identifier, payload.password)
        if current_user is None:
            record_audit_log(
                action="login_failed",
                target_type="user_account",
                target_id=payload.identifier,
                metadata={"identifier": payload.identifier},
                ip_address=ip_address,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid username or password",
            )
        session = create_user_session(current_user, request=request)
        attach_auth_cookies(response, session)
        record_audit_log(
            actor_user_id=current_user.id,
            action="login_success",
            target_type="user_account",
            target_id=str(current_user.id),
            metadata={"identifier": current_user.username},
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
        )
        return current_user.to_dict()

    @app.get("/api/auth/me")
    def auth_me(current_user: CurrentUser = Depends(require_current_user)):
        return current_user.to_dict()

    @app.post("/api/auth/logout")
    def logout(
        request: Request,
        response: Response,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        revoke_user_session(request=request)
        clear_auth_cookies(response)
        record_audit_log(
            actor_user_id=current_user.id,
            action="logout",
            target_type="user_account",
            target_id=str(current_user.id),
            metadata={"identifier": current_user.username},
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
        return {"ok": True}

    @app.get("/api/admin/users")
    def admin_list_users(_current_user: CurrentUser = Depends(require_admin_user)):
        return {"items": list_user_accounts()}

    @app.post("/api/admin/users")
    def admin_create_user(
        payload: AdminCreateUserPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_admin_user),
        _: None = Depends(require_csrf),
    ):
        try:
            return create_user_account(
                username=payload.username,
                email=payload.email,
                display_name=payload.display_name,
                password=payload.password,
                role=payload.role,
                actor_user_id=current_user.id,
                ip_address=request.client.host if request.client is not None else None,
                user_agent=request.headers.get("user-agent"),
            )
        except psycopg_errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="user already exists") from exc

    @app.post("/api/admin/users/{user_id}/reset-password")
    def admin_reset_password(
        user_id: int,
        payload: ResetPasswordPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_admin_user),
        _: None = Depends(require_csrf),
    ):
        if not reset_user_password(
            user_id=user_id,
            password=payload.password,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        ):
            raise HTTPException(status_code=404, detail="user not found")
        return {"ok": True}

    @app.post("/api/admin/users/{user_id}/disable")
    def admin_disable_user(
        user_id: int,
        request: Request,
        current_user: CurrentUser = Depends(require_admin_user),
        _: None = Depends(require_csrf),
    ):
        try:
            if not disable_user_account(
                user_id=user_id,
                actor_user_id=current_user.id,
                ip_address=request.client.host if request.client is not None else None,
                user_agent=request.headers.get("user-agent"),
            ):
                raise HTTPException(status_code=404, detail="user not found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/admin/users/{user_id}/enable")
    def admin_enable_user(
        user_id: int,
        request: Request,
        current_user: CurrentUser = Depends(require_admin_user),
        _: None = Depends(require_csrf),
    ):
        if not enable_user_account(
            user_id=user_id,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        ):
            raise HTTPException(status_code=404, detail="user not found")
        return {"ok": True}

    @app.get("/api/my/watchlist")
    def my_watchlist(current_user: CurrentUser = Depends(require_current_user)):
        return {"items": list_user_watchlist_items(user_id=current_user.id)}

    @app.post("/api/my/watchlist/items")
    def create_my_watchlist_item(
        payload: WatchlistItemPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        try:
            return create_user_watchlist_item(
                user_id=current_user.id,
                asset_id=payload.asset_id,
                source=payload.source,
                notes=payload.notes,
                actor_user_id=current_user.id,
                ip_address=request.client.host if request.client is not None else None,
                user_agent=request.headers.get("user-agent"),
            )
        except psycopg_errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="watchlist item already exists") from exc

    @app.patch("/api/my/watchlist/items/{asset_id}")
    def update_my_watchlist_item(
        asset_id: str,
        payload: WatchlistItemUpdatePayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        item = update_user_watchlist_item(
            user_id=current_user.id,
            asset_id=asset_id,
            source=payload.source,
            notes=payload.notes,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="watchlist item not found")
        return item

    @app.delete("/api/my/watchlist/items/{asset_id}")
    def delete_my_watchlist_item(
        asset_id: str,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        if not soft_delete_user_watchlist_item(
            user_id=current_user.id,
            asset_id=asset_id,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        ):
            raise HTTPException(status_code=404, detail="watchlist item not found")
        return {"ok": True}

    @app.get("/api/my/reviews")
    def my_reviews(current_user: CurrentUser = Depends(require_current_user)):
        return {"items": list_user_review_sessions(user_id=current_user.id)}

    @app.get("/api/my/reviews/{session_id}")
    def my_review_session(
        session_id: int,
        current_user: CurrentUser = Depends(require_current_user),
    ):
        session = get_user_review_session(user_id=current_user.id, session_id=session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="review session not found")
        return session

    @app.post("/api/my/reviews")
    def create_my_review_session(
        payload: ReviewSessionPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        return create_user_review_session(
            user_id=current_user.id,
            trade_date=payload.trade_date,
            title=payload.title,
            summary=payload.summary,
            market_view=payload.market_view,
            position_view=payload.position_view,
            next_action=payload.next_action,
            items=[item.model_dump(exclude_none=True) for item in payload.items],
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )

    @app.patch("/api/my/reviews/{session_id}")
    def update_my_review_session(
        session_id: int,
        payload: ReviewSessionPatchPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        session = update_user_review_session(
            user_id=current_user.id,
            session_id=session_id,
            trade_date=payload.trade_date,
            title=payload.title,
            summary=payload.summary,
            market_view=payload.market_view,
            position_view=payload.position_view,
            next_action=payload.next_action,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
        if session is None:
            raise HTTPException(status_code=404, detail="review session not found")
        return session

    @app.post("/api/my/reviews/{session_id}/items")
    def create_my_review_item(
        session_id: int,
        payload: ReviewItemPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        item = create_user_review_item(
            user_id=current_user.id,
            session_id=session_id,
            asset_id=payload.asset_id,
            decision=payload.decision,
            conviction=payload.conviction,
            tags=payload.tags,
            notes=payload.notes,
            follow_up_required=payload.follow_up_required,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="review session not found")
        return item

    @app.patch("/api/my/reviews/{session_id}/items/{item_id}")
    def update_my_review_item(
        session_id: int,
        item_id: int,
        payload: ReviewItemPatchPayload,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        item = update_user_review_item(
            user_id=current_user.id,
            session_id=session_id,
            item_id=item_id,
            decision=payload.decision,
            conviction=payload.conviction,
            tags=payload.tags,
            notes=payload.notes,
            follow_up_required=payload.follow_up_required,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="review item not found")
        return item

    @app.delete("/api/my/reviews/{session_id}")
    def delete_my_review_session(
        session_id: int,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        if not soft_delete_user_review_session(
            user_id=current_user.id,
            session_id=session_id,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        ):
            raise HTTPException(status_code=404, detail="review session not found")
        return {"ok": True}

    @app.delete("/api/my/reviews/{session_id}/items/{item_id}")
    def delete_my_review_item(
        session_id: int,
        item_id: int,
        request: Request,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        if not soft_delete_user_review_item(
            user_id=current_user.id,
            session_id=session_id,
            item_id=item_id,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
        ):
            raise HTTPException(status_code=404, detail="review item not found")
        return {"ok": True}

    @app.get("/api/dashboard/overview")
    def dashboard_overview(
        trade_date: str,
        score_version: str = "manual_v1",
        watchlist_id: str = "default",
        top_n: int = 30,
    ):
        return build_dashboard_overview(trade_date, score_version, watchlist_id, top_n)

    @app.get("/api/data/status")
    def data_status():
        return load_data_status_for_dashboard()

    @app.get("/api/intraday/status")
    def intraday_status(date: str | None = None):
        config = IntradayConfig.from_env()
        run_date = parse_trade_date(date, config.timezone)
        return load_intraday_status(config.service, run_date)

    @app.get("/api/public-news")
    def public_news(
        source: str | None = None,
        category: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return load_public_news_for_dashboard(
            source=source,
            category=category,
            q=q,
            limit=limit,
            offset=offset,
        )

    @app.post("/api/public-news/refresh")
    def public_news_refresh():
        return refresh_public_news_for_dashboard()

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
    def asset_bars(
        asset_id: str,
        end_date: str,
        start_date: str | None = None,
        adjust_type: str = "qfq",
        resolution: str = "1D",
        source: str = "akshare",
    ):
        resolved_resolution = normalize_resolution(resolution)
        return {
            "asset_id": asset_id,
            "resolution": resolved_resolution,
            "items": load_bars(
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
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

    return app


app = create_app()
