import json

import pytest

from stock_research.operator_decision.shadow_review_decisions_read_model import (
    import_shadow_review_decisions,
    load_shadow_review_decision_read_model_rows,
)


def _payload(run_id: str = "p16-shadow-review-decisions-2026-08-29") -> dict:
    return {
        "run_id": run_id,
        "decision_date": "2026-08-29",
        "status": "shadow_review_decisions_ready",
        "operator_id": "operator-a",
        "source_p15_review_run_ids": ["p15-shadow-analytics-review-2026-06-30-2026-08-29"],
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "group_count": 1,
        "groups": [
            {
                "decision_group_id": "artifact-provided-id-must-be-ignored",
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
                "review_status": "research_follow_up_candidate",
                "review_bucket": "follow_up",
                "decision_status": "open_research_follow_up",
                "decision_bucket": "research_follow_up",
                "decision_reason": "P15 review maps to follow-up.",
                "required_next_action": "Create a separate research follow-up.",
                "evidence_summary": "Forward return and drawdown clear follow-up thresholds.",
                "risk_notes": "Requires operator review before any production use.",
                "next_research_question": "Does this group remain stable across a longer window?",
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


def test_load_shadow_review_decision_read_model_rows_preserves_run_group_safety_and_lineage(tmp_path):
    json_path = tmp_path / "operator_shadow_review_decisions_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_review_decision_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p16-shadow-review-decisions-2026-08-29"
    assert rows["run"]["operator_id"] == "operator-a"
    assert rows["run"]["source_p15_review_run_ids"] == [
        "p15-shadow-analytics-review-2026-06-30-2026-08-29"
    ]
    assert rows["run"]["group_count"] == 1
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False
    assert rows["run"]["production_watchlist_enabled"] is False
    assert rows["run"]["production_write_enabled"] is False
    assert rows["run"]["groups_csv_path"] == str(tmp_path / "operator_shadow_review_decisions_2026-08-29_groups.csv")
    assert rows["run"]["markdown_path"] == str(tmp_path / "operator_shadow_review_decisions_2026-08-29.md")

    group = rows["groups"][0]
    assert group["decision_group_id"].startswith(
        "operator_shadow_review_decision:p16-shadow-review-decisions-2026-08-29:"
    )
    assert group["decision_group_id"] != "artifact-provided-id-must-be-ignored"
    assert group["source_p15_review_group_id"] == "operator_shadow_analytics_review:p15-run:abc123"
    assert group["source_p14_analytics_group_id"] == "operator_shadow_outcome_analytics:p14-run:abc123"
    assert group["decision_status"] == "open_research_follow_up"
    assert group["decision_bucket"] == "research_follow_up"
    assert group["manual_review_required"] is True
    assert group["auto_trade_enabled"] is False
    assert group["production_watchlist_enabled"] is False
    assert group["production_write_enabled"] is False


def test_load_shadow_review_decision_read_model_rows_rejects_production_write_enabled(tmp_path):
    payload = _payload()
    payload["production_write_enabled"] = True
    json_path = tmp_path / "operator_shadow_review_decisions_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_shadow_review_decision_read_model_rows(json_path)


def test_load_shadow_review_decision_read_model_rows_rejects_group_production_write_enabled(tmp_path):
    payload = _payload()
    payload["groups"][0]["production_write_enabled"] = True
    json_path = tmp_path / "operator_shadow_review_decisions_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_shadow_review_decision_read_model_rows(json_path)


def test_import_shadow_review_decisions_upserts_run_and_group(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_review_decisions_read_model

    json_path = tmp_path / "operator_shadow_review_decisions_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_review_decisions_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_review_decisions(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["group_count"] == 1
    assert result["run_ids"] == ["p16-shadow-review-decisions-2026-08-29"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_review_decision_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    assert isinstance(run_params["source_p15_review_run_ids"], str)
    group_sql, group_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_review_decision_group" in group_sql
    assert "ON CONFLICT (decision_group_id)" in group_sql
    assert group_params["decision_status"] == "open_research_follow_up"


def test_import_shadow_review_decisions_directory_imports_sorted_artifacts(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_review_decisions_read_model

    later_path = tmp_path / "operator_shadow_review_decisions_2026-09-30.json"
    earlier_path = tmp_path / "operator_shadow_review_decisions_2026-08-29.json"
    ignored_path = tmp_path / "not_a_p16_decision.json"
    later_path.write_text(json.dumps(_payload("p16-later")), encoding="utf-8")
    earlier_path.write_text(json.dumps(_payload("p16-earlier")), encoding="utf-8")
    ignored_path.write_text(json.dumps(_payload("ignored")), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_review_decisions_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_review_decisions(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["group_count"] == 2
    assert result["run_ids"] == ["p16-earlier", "p16-later"]
    run_params = [params for _sql, params in conn.cursor_obj.calls[::2]]
    assert [params["run_id"] for params in run_params] == ["p16-earlier", "p16-later"]
