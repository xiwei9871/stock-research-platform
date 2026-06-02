import json

import pytest

from stock_research.operator_decision.shadow_follow_up_resolution_read_model import (
    import_shadow_follow_up_resolution,
    load_shadow_follow_up_resolution_read_model_rows,
)


def _payload(run_id: str = "p18-shadow-follow-up-resolution-2026-08-29") -> dict:
    return {
        "run_id": run_id,
        "resolution_date": "2026-08-29",
        "status": "shadow_follow_up_resolution_ready",
        "operator_id": "operator-a",
        "source_p17_follow_up_run_ids": ["p17-shadow-follow-up-queue-2026-08-29"],
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "item_count": 1,
        "items": [
            {
                "resolution_item_id": "artifact-provided-id-must-be-ignored",
                "source_p17_follow_up_item_id": "operator_shadow_follow_up:p17-run:abc123",
                "source_p17_follow_up_run_id": "p17-shadow-follow-up-queue-2026-08-29",
                "source_p16_decision_group_id": "operator_shadow_review_decision:p16-run:abc123",
                "source_p16_decision_run_id": "p16-shadow-review-decisions-2026-08-29",
                "source_p15_review_group_id": "operator_shadow_analytics_review:p15-run:abc123",
                "source_p15_review_run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
                "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14-run:abc123",
                "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 12,
                "complete_count": 11,
                "insufficient_data_count": 1,
                "review_status": "needs_more_data",
                "review_bucket": "data_needed",
                "decision_status": "request_more_data",
                "decision_bucket": "data_needed",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "required_input": "Additional outcome or data-quality evidence",
                "resolution_status": "stale_unresolved",
                "resolution_bucket": "needs_operator_review",
                "recommended_resolution_action": "Review whether the requested evidence has been collected.",
                "resolution_reason": "P17 follow-up maps to stale unresolved.",
                "follow_up_reason": "P16 decision maps to data collection.",
                "decision_reason": "P15 review maps to more data.",
                "required_next_action": "Collect additional evidence.",
                "evidence_summary": "Single sample is not enough.",
                "risk_notes": "Data coverage may be incomplete.",
                "next_research_question": "Does the group remain stable with more samples?",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
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

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_follow_up_resolution_read_model_rows_preserves_run_item_safety_and_lineage(tmp_path):
    json_path = tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_follow_up_resolution_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p18-shadow-follow-up-resolution-2026-08-29"
    assert rows["run"]["operator_id"] == "operator-a"
    assert rows["run"]["source_p17_follow_up_run_ids"] == ["p17-shadow-follow-up-queue-2026-08-29"]
    assert rows["run"]["item_count"] == 1
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False
    assert rows["run"]["production_watchlist_enabled"] is False
    assert rows["run"]["production_write_enabled"] is False
    assert rows["run"]["items_csv_path"] == str(
        tmp_path / "operator_shadow_follow_up_resolution_2026-08-29_items.csv"
    )
    assert rows["run"]["markdown_path"] == str(tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.md")

    item = rows["items"][0]
    assert item["resolution_item_id"].startswith(
        "operator_shadow_follow_up_resolution:p18-shadow-follow-up-resolution-2026-08-29:"
    )
    assert item["resolution_item_id"] != "artifact-provided-id-must-be-ignored"
    assert item["source_p17_follow_up_item_id"] == "operator_shadow_follow_up:p17-run:abc123"
    assert item["source_p16_decision_group_id"] == "operator_shadow_review_decision:p16-run:abc123"
    assert item["source_p15_review_group_id"] == "operator_shadow_analytics_review:p15-run:abc123"
    assert item["source_p14_analytics_group_id"] == "operator_shadow_outcome_analytics:p14-run:abc123"
    assert item["resolution_status"] == "stale_unresolved"
    assert item["resolution_bucket"] == "needs_operator_review"
    assert item["manual_review_required"] is True
    assert item["auto_trade_enabled"] is False
    assert item["production_watchlist_enabled"] is False
    assert item["production_write_enabled"] is False


def test_load_shadow_follow_up_resolution_read_model_rows_rejects_production_write_enabled(tmp_path):
    payload = _payload()
    payload["production_write_enabled"] = True
    json_path = tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_shadow_follow_up_resolution_read_model_rows(json_path)


def test_load_shadow_follow_up_resolution_read_model_rows_rejects_item_production_write_enabled(tmp_path):
    payload = _payload()
    payload["items"][0]["production_write_enabled"] = True
    json_path = tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_shadow_follow_up_resolution_read_model_rows(json_path)


def test_import_shadow_follow_up_resolution_upserts_run_and_item(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_follow_up_resolution_read_model

    json_path = tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_follow_up_resolution_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_follow_up_resolution(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["item_count"] == 1
    assert result["run_ids"] == ["p18-shadow-follow-up-resolution-2026-08-29"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_follow_up_resolution_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    assert isinstance(run_params["source_p17_follow_up_run_ids"], str)
    item_sql, item_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_follow_up_resolution_item" in item_sql
    assert "ON CONFLICT (resolution_item_id)" in item_sql
    assert item_params["resolution_status"] == "stale_unresolved"


def test_import_shadow_follow_up_resolution_directory_imports_sorted_artifacts(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_follow_up_resolution_read_model

    later_path = tmp_path / "operator_shadow_follow_up_resolution_2026-09-30.json"
    earlier_path = tmp_path / "operator_shadow_follow_up_resolution_2026-08-29.json"
    ignored_path = tmp_path / "not_a_p18_resolution.json"
    later_path.write_text(json.dumps(_payload("p18-later")), encoding="utf-8")
    earlier_path.write_text(json.dumps(_payload("p18-earlier")), encoding="utf-8")
    ignored_path.write_text(json.dumps(_payload("ignored")), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_follow_up_resolution_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_follow_up_resolution(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["item_count"] == 2
    assert result["run_ids"] == ["p18-earlier", "p18-later"]
    run_params = [params for _sql, params in conn.cursor_obj.calls[::2]]
    assert [params["run_id"] for params in run_params] == ["p18-earlier", "p18-later"]
