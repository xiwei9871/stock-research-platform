from fastapi.testclient import TestClient
from psycopg import errors as psycopg_errors

from stock_research import cli
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import shadow_outcomes


def test_overview_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_dashboard_overview",
        lambda trade_date, score_version, watchlist_id, top_n: {
            "trade_date": trade_date,
            "score_version": score_version,
            "watchlist_id": watchlist_id,
            "top_scores": [],
            "watchlist_signals": [],
            "reports": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/dashboard/overview?trade_date=2026-05-29")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-05-29"


def test_public_news_route_returns_filtered_items(monkeypatch):
    captured = {}

    def fake_load_public_news(**kwargs):
        captured.update(kwargs)
        return {
            "items": [{"news_id": "news-1", "title": "全球快讯", "category": "live"}],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "load_public_news_for_dashboard", fake_load_public_news)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF&limit=10&offset=2"
    )

    assert response.status_code == 200
    assert captured == {
        "source": "sina_finance",
        "category": "live",
        "q": "快讯",
        "limit": 10,
        "offset": 2,
    }
    assert response.json()["items"][0]["title"] == "全球快讯"


def test_public_news_refresh_route_returns_counts(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "refresh_public_news_for_dashboard",
        lambda: {
            "received": 2,
            "stored": 2,
            "items_received": 2,
            "counts_by_category": {"live": 2},
            "warnings": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/public-news/refresh")

    assert response.status_code == 200
    assert response.json()["counts_by_category"] == {"live": 2}


def test_asset_detail_route_returns_404_for_missing_asset(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_asset_detail", lambda asset_id: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/000001.SZ")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found"


def test_minute_bars_route_passes_source(monkeypatch):
    captured = {}

    def fake_load_minute_bars(asset_id, start_time, end_time, freq, adjust_type, source):
        captured["args"] = [asset_id, start_time, end_time, freq, adjust_type, source]
        return [{"time": "2026-05-29 09:35:00"}]

    monkeypatch.setattr(dashboard_app, "load_minute_bars", fake_load_minute_bars)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/minute-bars"
        "?start_time=2026-05-29T09:30:00"
        "&end_time=2026-05-29T15:00:00"
        "&freq=5min"
        "&adjust_type=qfq"
        "&source=tushare"
    )

    assert response.status_code == 200
    assert captured["args"] == [
        "000001.SZ",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
        "tushare",
    ]
    assert response.json()["items"] == [{"time": "2026-05-29 09:35:00"}]


def test_asset_decisions_route_returns_read_only_history(monkeypatch):
    captured = {}

    def fake_load_decision_history(asset_id, start_date, end_date, limit):
        captured["args"] = [asset_id, start_date, end_date, limit]
        return [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "event_id": "operator_decision:morning-review:0:abc",
                "asset_id": asset_id,
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "notes": "strong score",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_asset_decision_history", fake_load_decision_history)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/decisions"
        "?start_date=2026-05-01"
        "&end_date=2026-05-30"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["000001.SZ", "2026-05-01", "2026-05-30", 10]
    assert response.json()["items"][0]["decision_label"] == "candidate"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_asset_outcomes_route_returns_read_only_history(monkeypatch):
    captured = {}

    def fake_load_outcome_history(asset_id, start_date, end_date, review_session_id, limit):
        captured["args"] = [asset_id, start_date, end_date, review_session_id, limit]
        return [
            {
                "outcome_event_id": "operator_decision_outcome:p8:abc",
                "run_id": "p8-outcome-2026-05-01-2026-05-30",
                "decision_event_id": "operator_decision:morning-review:0:abc",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": asset_id,
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "source_context": "dashboard_topn",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-05-30",
                "base_close": 10.0,
                "forward_returns": {"1": 0.1, "5": 0.2},
                "max_high_returns": {"1": 0.12, "5": 0.25},
                "max_low_drawdowns": {"1": 0.0, "5": -0.04},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/operator_decision_journal.json",
                "outcome_artifact_path": "outputs/p8/operator_decision_outcome_review.json",
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_asset_outcome_history", fake_load_outcome_history)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/outcomes"
        "?start_date=2026-05-01"
        "&end_date=2026-05-30"
        "&review_session_id=morning-review"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["000001.SZ", "2026-05-01", "2026-05-30", "morning-review", 10]
    assert response.json()["items"][0]["outcome_status"] == "complete"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_analytics_review_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_review(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "review_group_id": "operator_shadow_analytics_review:trend-ready",
                "run_id": "p15-shadow-analytics-review-2026-08-31",
                "review_start_date": "2026-06-01",
                "review_end_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "horizon_metrics": {"20": {"forward_return_mean": 0.12}},
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "evidence_summary": "Positive 20D mean with incomplete samples.",
                "risk_notes": "Observe only.",
                "next_research_question": "Can drawdown improve under stricter filters?",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_analytics_review_summary",
        fake_load_review,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-analytics-review"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["review_status"] == "research_follow_up_candidate"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_review_decisions_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_decisions(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "decision_group_id": "operator_shadow_review_decision:trend-ready",
                "run_id": "p16-shadow-review-decisions-2026-08-31",
                "decision_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "decision_status": "open_research_follow_up",
                "decision_bucket": "research_follow_up",
                "decision_reason": "P15 status maps to follow-up.",
                "required_next_action": "Create a separately scoped research follow-up.",
                "evidence_summary": "Positive 20D mean with incomplete samples.",
                "risk_notes": "Observe only.",
                "next_research_question": "Can drawdown improve under stricter filters?",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_review_decision_summary",
        fake_load_decisions,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-review-decisions"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["decision_status"] == "open_research_follow_up"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_follow_up_queue_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_follow_up(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "follow_up_item_id": "operator_shadow_follow_up:trend-ready",
                "run_id": "p17-shadow-follow-up-queue-2026-08-31",
                "follow_up_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "decision_status": "request_more_data",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "required_input": "Additional outcome or data-quality evidence",
                "follow_up_reason": "P16 status maps to evidence collection.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_follow_up_queue_summary",
        fake_load_follow_up,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-follow-up-queue"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["follow_up_status"] == "collect_more_evidence"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_shadow_follow_up_resolution_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_resolution(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "resolution_item_id": "operator_shadow_follow_up_resolution:trend-ready",
                "run_id": "p18-shadow-follow-up-resolution-2026-08-31",
                "resolution_date": "2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "resolution_status": "stale_unresolved",
                "resolution_bucket": "needs_operator_review",
                "recommended_resolution_action": "Review whether requested evidence has been collected.",
                "resolution_reason": "P17 follow-up maps to stale unresolved.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(
        dashboard_app,
        "load_shadow_follow_up_resolution_summary",
        fake_load_resolution,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-follow-up-resolution"
        "?start_date=2026-06-01"
        "&end_date=2026-08-31"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["resolution_status"] == "stale_unresolved"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_outcome_analytics_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_analytics(start_date, end_date, review_session_id, limit):
        captured["args"] = [start_date, end_date, review_session_id, limit]
        return [
            {
                "run_id": "p9-outcome-analytics-2026-05-01-2026-06-30",
                "review_start_date": "2026-05-01",
                "review_end_date": "2026-06-30",
                "analytics_level": "decision_label",
                "group_value": "candidate",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "follow_up_required_rate": 0.5,
                "horizon_metrics": {"5": {"forward_return_mean": 0.15, "forward_win_rate": 1.0}},
                "analytics_artifact_path": "outputs/p9/operator_decision_outcome_analytics.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_outcome_analytics_summary", fake_load_analytics)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/outcome-analytics"
        "?start_date=2026-05-01"
        "&end_date=2026-06-30"
        "&review_session_id=morning-review"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-05-01", "2026-06-30", "morning-review", 10]
    assert response.json()["items"][0]["analytics_level"] == "decision_label"
    assert response.json()["items"][0]["auto_trade_enabled"] is False


def test_experiment_proposals_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_proposals(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "proposal_id": "p10-proposal:001",
                "run_id": "p10-proposals-2026-05-31",
                "review_date": "2026-05-31",
                "proposal_title": "Replay dashboard top-N",
                "hypothesis": "Dashboard top-N candidates should be replayed offline.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:candidate"],
                "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
                "source_artifact_paths": ["outputs/p9/analytics.json"],
                "expected_validation_method": "offline replay",
                "risk_notes": "No production scoring change in P10.",
                "reviewer_id": "reviewer-a",
                "status": "approved_for_experiment",
                "proposal_artifact_path": "outputs/p10/operator_experiment_proposals_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "promotion_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_experiment_proposals_summary", fake_load_proposals)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/experiment-proposals"
        "?start_date=2026-05-01"
        "&end_date=2026-06-30"
        "&status=approved_for_experiment"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-05-01", "2026-06-30", "approved_for_experiment", 10]
    assert response.json()["items"][0]["proposal_id"] == "p10-proposal:001"
    assert response.json()["items"][0]["promotion_enabled"] is False


def test_experiment_replay_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_replay(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-05-31",
                "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
                "validation_method": "offline replay",
                "replay_status": "passed_offline_replay",
                "sample_count": 24,
                "passed_count": 18,
                "failed_count": 6,
                "metric_summary": {"win_rate": 0.75},
                "failure_reason": "",
                "defer_reason": "",
                "replay_artifact_path": "outputs/p11/operator_experiment_replay_2026-01-01_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_experiment_replay_summary", fake_load_replay)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/experiment-replay"
        "?start_date=2026-01-01"
        "&end_date=2026-06-30"
        "&status=passed_offline_replay"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-01-01", "2026-06-30", "passed_offline_replay", 10]
    assert response.json()["items"][0]["replay_result_id"] == "p11-replay:001"
    assert response.json()["items"][0]["auto_trade_enabled"] is False
    assert response.json()["items"][0]["production_write_enabled"] is False


def test_shadow_watchlist_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_watchlist_summary", fake_load_shadow)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-watchlist"
        "?start_date=2026-06-01"
        "&end_date=2026-06-30"
        "&status=shadow_ready"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-06-30", "shadow_ready", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False


def test_shadow_outcomes_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow_outcomes(start_date, end_date, outcome_status, limit):
        captured["args"] = [start_date, end_date, outcome_status, limit]
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": {"5": 0.5},
                "max_high_returns": {"5": 0.6},
                "max_low_drawdowns": {"5": -0.1},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_outcomes_summary", fake_load_shadow_outcomes)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcomes"
        "?start_date=2026-06-01"
        "&end_date=2026-07-31"
        "&outcome_status=complete"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-07-31", "complete", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False


def test_shadow_outcomes_route_returns_empty_items_when_table_missing(monkeypatch):
    class FakeConnect:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing P13 outcome table")

    monkeypatch.setattr(shadow_outcomes, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(shadow_outcomes, "connect", fake_connect)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/shadow-outcomes?start_date=2026-06-01&end_date=2026-07-31")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_shadow_outcome_analytics_route_returns_read_only_summary(monkeypatch):
    captured = {}
    rows = [
        {
            "analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
            "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
            "review_start_date": "2026-06-30",
            "review_end_date": "2026-08-29",
            "group_key": "trend_shadow|shadow_ready",
            "shadow_layer": "trend_shadow",
            "shadow_status": "shadow_ready",
            "sample_count": 2,
            "complete_count": 2,
            "insufficient_data_count": 0,
            "source_p12_shadow_run_count": 1,
            "source_p11_replay_run_count": 1,
            "source_p10_proposal_run_count": 1,
            "source_p9_analytics_run_count": 1,
            "horizon_metrics": {"20": {"forward_return_mean": 0.12}},
            "analytics_artifact_path": "outputs/p14/analytics.json",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    ]

    def fake_load_analytics(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return rows

    monkeypatch.setattr(dashboard_app, "load_shadow_outcome_analytics_summary", fake_load_analytics)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcome-analytics?start_date=2026-06-01&end_date=2026-08-31&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json() == {"items": rows}


def test_dashboard_api_cli_parser_accepts_host_and_port():
    args = cli.build_parser().parse_args(
        ["dashboard-api", "--host", "0.0.0.0", "--port", "9999"]
    )

    assert args.command == "dashboard-api"
    assert args.host == "0.0.0.0"
    assert args.port == 9999


def test_dashboard_api_cli_dispatches_to_runner(monkeypatch):
    captured = {}

    def fake_run_dashboard_api(host, port):
        captured["call"] = {"host": host, "port": port}

    monkeypatch.setattr(cli, "run_dashboard_api", fake_run_dashboard_api)

    cli.main_for_args(["dashboard-api", "--host", "0.0.0.0", "--port", "9999"])

    assert captured["call"] == {"host": "0.0.0.0", "port": 9999}
