import json

import pytest

from stock_research.operator_decision.shadow_watchlist_read_model import (
    import_shadow_watchlist_review,
    load_shadow_watchlist_read_model_rows,
)


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def _payload() -> dict:
    return {
        "run_id": "p12-shadow-watchlist-2026-06-30",
        "review_date": "2026-06-30",
        "status": "shadow_watchlist_review_ready",
        "candidate_count": 1,
        "status_counts": {"shadow_ready": 1},
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "candidates": [
            {
                "shadow_candidate_id": "p12-shadow:001",
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
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }


def test_load_shadow_watchlist_rows_preserves_sources_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_watchlist_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["candidates_csv_path"].endswith("_candidates.csv")
    assert rows["run"]["production_watchlist_enabled"] is False
    candidate = rows["candidates"][0]
    assert candidate["shadow_candidate_id"] == "p12-shadow:001"
    assert candidate["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert candidate["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert candidate["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert candidate["shadow_artifact_path"] == str(json_path)
    assert candidate["production_watchlist_enabled"] is False


def test_load_shadow_watchlist_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_watchlist_read_model_rows(json_path)


def test_import_shadow_watchlist_review_upserts_run_and_candidates(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_watchlist_read_model

    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_watchlist_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_watchlist_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["candidate_count"] == 1
    assert result["run_ids"] == ["p12-shadow-watchlist-2026-06-30"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    candidate_sql, candidate_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_candidate" in candidate_sql
    assert "ON CONFLICT (shadow_candidate_id)" in candidate_sql
    assert candidate_params["shadow_candidate_id"] == "p12-shadow:001"
