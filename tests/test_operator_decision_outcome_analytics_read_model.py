import json

import pytest

from stock_research.operator_decision.outcome_analytics_read_model import (
    import_decision_outcome_analytics,
    load_decision_outcome_analytics_read_model_rows,
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


def _analytics_payload() -> dict:
    return {
        "run_id": "p9-outcome-analytics-2026-05-01-2026-06-30",
        "review_start_date": "2026-05-01",
        "review_end_date": "2026-06-30",
        "status": "analytics_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "horizons": [1, 5],
        "source_outcome_count": 2,
        "group_count": 2,
        "diagnostic_count": 1,
        "groups": [
            {
                "analytics_level": "decision_label",
                "decision_label": "candidate",
                "source_context": "",
                "review_session_id": "",
                "asset_id": "",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "follow_up_required_rate": 0.5,
                "forward_1d_return_mean": 0.04,
                "forward_1d_return_median": 0.04,
                "forward_1d_win_rate": 0.5,
                "max_high_return_1d_mean": 0.065,
                "max_low_drawdown_1d_mean": -0.015,
                "max_low_drawdown_1d_worst": -0.03,
                "forward_5d_return_mean": 0.15,
                "forward_5d_return_median": 0.15,
                "forward_5d_win_rate": 1.0,
                "max_high_return_5d_mean": 0.20,
                "max_low_drawdown_5d_mean": -0.06,
                "max_low_drawdown_5d_worst": -0.08,
            },
            {
                "analytics_level": "source_context",
                "decision_label": "",
                "source_context": "dashboard_topn",
                "review_session_id": "",
                "asset_id": "",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "follow_up_required_rate": 0.5,
                "forward_1d_return_mean": 0.04,
                "forward_1d_return_median": 0.04,
                "forward_1d_win_rate": 0.5,
                "max_high_return_1d_mean": 0.065,
                "max_low_drawdown_1d_mean": -0.015,
                "max_low_drawdown_1d_worst": -0.03,
                "forward_5d_return_mean": 0.15,
                "forward_5d_return_median": 0.15,
                "forward_5d_win_rate": 1.0,
                "max_high_return_5d_mean": 0.20,
                "max_low_drawdown_5d_mean": -0.06,
                "max_low_drawdown_5d_worst": -0.08,
            },
        ],
        "diagnostics": [
            {
                "diagnostic_type": "top_forward_return",
                "horizon": 5,
                "analytics_level": "decision_label",
                "group_value": "candidate",
                "metric_column": "forward_5d_return_mean",
                "metric_value": 0.15,
            }
        ],
    }


def test_load_decision_outcome_analytics_rows_preserves_artifact_paths_and_metrics(tmp_path):
    json_path = tmp_path / "operator_decision_outcome_analytics_2026-05-01_2026-06-30.json"
    json_path.write_text(json.dumps(_analytics_payload()), encoding="utf-8")

    rows = load_decision_outcome_analytics_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p9-outcome-analytics-2026-05-01-2026-06-30"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["groups_csv_path"].endswith("_groups.csv")
    assert rows["run"]["diagnostics_csv_path"].endswith("_diagnostics.csv")
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False

    group = rows["groups"][0]
    assert group["run_id"] == "p9-outcome-analytics-2026-05-01-2026-06-30"
    assert group["analytics_level"] == "decision_label"
    assert group["group_value"] == "candidate"
    assert group["review_start_date"] == "2026-05-01"
    assert group["review_end_date"] == "2026-06-30"
    assert group["analytics_artifact_path"] == str(json_path)
    assert group["horizon_metrics"]["1"]["forward_return_mean"] == 0.04
    assert group["horizon_metrics"]["5"]["max_low_drawdown_worst"] == -0.08


def test_load_decision_outcome_analytics_rows_rejects_execution_enabled_artifact(tmp_path):
    payload = _analytics_payload()
    payload["auto_trade_enabled"] = True
    json_path = tmp_path / "operator_decision_outcome_analytics_2026-05-01_2026-06-30.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="auto_trade_not_allowed"):
        load_decision_outcome_analytics_read_model_rows(json_path)


def test_import_decision_outcome_analytics_upserts_run_and_groups(monkeypatch, tmp_path):
    from stock_research.operator_decision import outcome_analytics_read_model

    json_path = tmp_path / "operator_decision_outcome_analytics_2026-05-01_2026-06-30.json"
    json_path.write_text(json.dumps(_analytics_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(outcome_analytics_read_model, "connect", lambda service: _Context(conn))

    result = import_decision_outcome_analytics(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["run_ids"] == ["p9-outcome-analytics-2026-05-01-2026-06-30"]
    assert result["group_count"] == 2
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_decision_outcome_analytics_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    group_sql, group_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_decision_outcome_analytics_group" in group_sql
    assert "ON CONFLICT (analytics_group_id)" in group_sql
    assert group_params["analytics_level"] == "decision_label"
    assert group_params["group_value"] == "candidate"
    assert group_params["analytics_artifact_path"] == str(json_path)


def test_import_decision_outcome_analytics_accepts_directory(monkeypatch, tmp_path):
    from stock_research.operator_decision import outcome_analytics_read_model

    first = _analytics_payload()
    second = {
        **_analytics_payload(),
        "run_id": "p9-outcome-analytics-2026-07-01-2026-07-31",
        "review_start_date": "2026-07-01",
        "review_end_date": "2026-07-31",
    }
    (tmp_path / "operator_decision_outcome_analytics_2026-05-01_2026-06-30.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "operator_decision_outcome_analytics_2026-07-01_2026-07-31.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(outcome_analytics_read_model, "connect", lambda service: _Context(conn))

    result = import_decision_outcome_analytics(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["run_ids"] == [
        "p9-outcome-analytics-2026-05-01-2026-06-30",
        "p9-outcome-analytics-2026-07-01-2026-07-31",
    ]
    assert result["group_count"] == 4
