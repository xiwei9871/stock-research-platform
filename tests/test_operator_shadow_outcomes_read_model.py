import json

import pytest

from stock_research.operator_decision.shadow_outcomes_read_model import (
    import_shadow_outcome_review,
    load_shadow_outcome_read_model_rows,
)


def _payload() -> dict:
    return {
        "run_id": "p13-shadow-outcomes-2026-07-31",
        "review_date": "2026-07-31",
        "status": "shadow_outcome_review_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": [1, 5],
        "outcome_count": 1,
        "outcomes": [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "available_future_bars": 5,
                "outcome_status": "complete",
                "forward_1d_return": 0.1,
                "forward_5d_return": 0.5,
                "max_high_return_5d": 0.6,
                "max_low_drawdown_5d": -0.1,
                "source_shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
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


def test_load_shadow_outcome_rows_preserves_sources_metrics_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_outcome_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["details_csv_path"].endswith("_details.csv")
    assert rows["run"]["production_watchlist_enabled"] is False
    candidate = rows["candidates"][0]
    assert candidate["shadow_candidate_id"] == "p12-shadow:001"
    assert candidate["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert candidate["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert candidate["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert candidate["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert candidate["forward_returns"] == {"1": 0.1, "5": 0.5}
    assert candidate["max_high_returns"] == {"5": 0.6}
    assert candidate["max_low_drawdowns"] == {"5": -0.1}
    assert candidate["production_write_enabled"] is False


def test_load_shadow_outcome_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_outcome_read_model_rows(json_path)


@pytest.mark.parametrize(
    "field",
    [
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ],
)
def test_load_shadow_outcome_rows_rejects_malformed_top_level_safety_values(tmp_path, field):
    payload = _payload()
    payload[field] = "maybe"
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=f"invalid_safety_field: {field}|{field}"):
        load_shadow_outcome_read_model_rows(json_path)


@pytest.mark.parametrize(
    "field",
    [
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ],
)
def test_load_shadow_outcome_rows_rejects_malformed_outcome_safety_values(tmp_path, field):
    payload = _payload()
    payload["outcomes"][0][field] = "maybe"
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=f"invalid_safety_field: {field}|{field}"):
        load_shadow_outcome_read_model_rows(json_path)


def test_load_shadow_outcome_rows_preserves_safe_run_scoped_artifact_ids(tmp_path):
    payload = _payload()
    payload["outcomes"][0]["shadow_outcome_id"] = "operator_shadow_outcome:p13-shadow-outcomes-2026-07-31:abc123"
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = load_shadow_outcome_read_model_rows(json_path)

    assert (
        rows["candidates"][0]["shadow_outcome_id"]
        == "operator_shadow_outcome:p13-shadow-outcomes-2026-07-31:abc123"
    )


def test_load_shadow_outcome_rows_normalizes_legacy_candidate_only_ids_by_run(tmp_path):
    first = _payload()
    second = _payload()
    first["run_id"] = "p13-shadow-outcomes-2026-07-31"
    second["run_id"] = "p13-shadow-outcomes-2026-08-01"
    first["outcomes"][0]["shadow_outcome_id"] = "p13-shadow-outcome:p12-shadow:001"
    second["outcomes"][0]["shadow_outcome_id"] = "p13-shadow-outcome:p12-shadow:001"
    first_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    second_path = tmp_path / "operator_shadow_outcomes_2026-08-01.json"
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path.write_text(json.dumps(second), encoding="utf-8")

    first_rows = load_shadow_outcome_read_model_rows(first_path)
    second_rows = load_shadow_outcome_read_model_rows(second_path)

    first_id = first_rows["candidates"][0]["shadow_outcome_id"]
    second_id = second_rows["candidates"][0]["shadow_outcome_id"]
    assert first_id != second_id
    assert first_id.startswith("operator_shadow_outcome:p13-shadow-outcomes-2026-07-31:")
    assert second_id.startswith("operator_shadow_outcome:p13-shadow-outcomes-2026-08-01:")


def test_import_shadow_outcome_review_upserts_run_and_candidates(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_outcomes_read_model

    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_outcomes_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_outcome_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["candidate_count"] == 1
    assert result["run_ids"] == ["p13-shadow-outcomes-2026-07-31"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    candidate_sql, candidate_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_candidate" in candidate_sql
    assert "ON CONFLICT (shadow_outcome_id)" in candidate_sql
    assert candidate_params["shadow_candidate_id"] == "p12-shadow:001"
