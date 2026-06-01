import json
import math

import pytest

from stock_research.operator_decision.shadow_outcome_analytics_read_model import (
    import_shadow_outcome_analytics,
    load_shadow_outcome_analytics_read_model_rows,
)


def _payload(run_id: str = "p14-shadow-outcome-analytics-2026-06-30-2026-08-29") -> dict:
    return {
        "run_id": run_id,
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "status": "shadow_outcome_analytics_ready",
        "group_by": ["shadow_layer", "shadow_status"],
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": [5, 20],
        "source_outcome_count": 3,
        "group_count": 1,
        "groups": [
            {
                "analytics_group_id": "artifact-provided-id-must-be-ignored",
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
                "forward_5d_return_mean": 0.04,
                "forward_5d_return_median": 0.04,
                "forward_5d_win_rate": 0.5,
                "forward_20d_return_mean": None,
                "max_high_return_20d_mean": 0.19,
                "max_low_drawdown_20d_mean": -0.085,
                "max_low_drawdown_20d_worst": -0.12,
                "max_high_return_5d_mean": math.nan,
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


def test_load_shadow_outcome_analytics_rows_preserves_group_metrics_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_outcome_analytics_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    assert rows["run"]["group_count"] == 1
    assert rows["run"]["production_watchlist_enabled"] is False
    assert rows["run"]["groups_csv_path"] == str(
        tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29_groups.csv"
    )
    group = rows["groups"][0]
    assert group["analytics_group_id"].startswith("operator_shadow_outcome_analytics:")
    assert group["analytics_group_id"] != "artifact-provided-id-must-be-ignored"
    assert group["group_key"] == "trend_shadow|shadow_ready"
    assert group["horizon_metrics"]["5"]["forward_return_mean"] == 0.04
    assert group["horizon_metrics"]["20"]["max_low_drawdown_worst"] == -0.12
    assert "forward_return_mean" not in group["horizon_metrics"]["20"]
    assert "max_high_return_mean" not in group["horizon_metrics"]["5"]
    assert group["production_write_enabled"] is False


def test_load_shadow_outcome_analytics_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_outcome_analytics_read_model_rows(json_path)


def test_load_shadow_outcome_analytics_rows_rejects_group_level_unsafe_value(tmp_path):
    payload = _payload()
    payload["groups"][0]["auto_trade_enabled"] = True
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="auto_trade_not_allowed"):
        load_shadow_outcome_analytics_read_model_rows(json_path)


def test_analytics_group_id_is_scoped_by_run_id(tmp_path):
    first_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    second_path = tmp_path / "operator_shadow_outcome_analytics_2026-09-01_2026-09-30.json"
    first_path.write_text(json.dumps(_payload("p14-run-a")), encoding="utf-8")
    second_path.write_text(json.dumps(_payload("p14-run-b")), encoding="utf-8")

    first_group = load_shadow_outcome_analytics_read_model_rows(first_path)["groups"][0]
    second_group = load_shadow_outcome_analytics_read_model_rows(second_path)["groups"][0]

    assert first_group["group_key"] == second_group["group_key"]
    assert first_group["analytics_group_id"] != second_group["analytics_group_id"]


def test_import_shadow_outcome_analytics_upserts_run_and_groups(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_outcome_analytics_read_model

    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_outcome_analytics_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_outcome_analytics(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["group_count"] == 1
    assert result["run_ids"] == ["p14-shadow-outcome-analytics-2026-06-30-2026-08-29"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    assert isinstance(run_params["metadata"], str)
    group_sql, group_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_group" in group_sql
    assert "ON CONFLICT (analytics_group_id)" in group_sql
    assert group_params["group_key"] == "trend_shadow|shadow_ready"
    assert isinstance(group_params["horizon_metrics"], str)
    assert isinstance(group_params["metadata"], str)


def test_import_shadow_outcome_analytics_accepts_directory_in_sorted_order(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_outcome_analytics_read_model

    (tmp_path / "ignore.json").write_text("{}", encoding="utf-8")
    later = tmp_path / "operator_shadow_outcome_analytics_2026-09-01_2026-09-30.json"
    earlier = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    later.write_text(json.dumps(_payload("p14-b")), encoding="utf-8")
    earlier.write_text(json.dumps(_payload("p14-a")), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_outcome_analytics_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_outcome_analytics(tmp_path, service="stock_research_test")

    assert result == {"imported_count": 2, "group_count": 2, "run_ids": ["p14-a", "p14-b"]}
