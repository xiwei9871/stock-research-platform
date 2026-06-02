import json

import pytest

from stock_research.operator_decision.outcome_read_model import (
    import_decision_outcome_review,
    load_decision_outcome_read_model_rows,
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


def _outcome_payload() -> dict:
    return {
        "run_id": "p8-outcome-2026-05-01-2026-05-30",
        "review_start_date": "2026-05-01",
        "review_end_date": "2026-05-30",
        "status": "review_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "horizons": [1, 5],
        "outcome_count": 1,
        "summary_count": 2,
        "outcomes": [
            {
                "event_id": "operator_decision:morning-review:0:aaa",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/operator_decision_journal_2026-05-30_morning-review.json",
                "outcome_status": "complete",
                "available_future_bars": 5,
                "base_trade_date": "2026-05-30",
                "base_close": 10.0,
                "forward_1d_return": 0.1,
                "max_high_return_1d": 0.2,
                "max_low_drawdown_1d": 0.0,
                "forward_5d_return": 0.5,
                "max_high_return_5d": 0.6,
                "max_low_drawdown_5d": -0.1,
            }
        ],
        "summary": [
            {
                "summary_level": "decision_label",
                "decision_label": "candidate",
                "source_context": "",
                "sample_count": 1,
                "complete_count": 1,
                "insufficient_data_count": 0,
            }
        ],
    }


def test_load_decision_outcome_read_model_rows_preserves_artifact_and_decision_paths(tmp_path):
    json_path = tmp_path / "operator_decision_outcome_review_2026-05-01_2026-05-30.json"
    json_path.write_text(json.dumps(_outcome_payload()), encoding="utf-8")

    rows = load_decision_outcome_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p8-outcome-2026-05-01-2026-05-30"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["details_csv_path"].endswith("_details.csv")
    assert rows["run"]["summary_csv_path"].endswith("_summary.csv")
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False

    event = rows["events"][0]
    assert event["run_id"] == "p8-outcome-2026-05-01-2026-05-30"
    assert event["decision_event_id"] == "operator_decision:morning-review:0:aaa"
    assert event["source_artifact_path"] == "outputs/p7/operator_decision_journal_2026-05-30_morning-review.json"
    assert event["outcome_artifact_path"] == str(json_path)
    assert event["forward_returns"] == {"1": 0.1, "5": 0.5}
    assert event["max_high_returns"] == {"1": 0.2, "5": 0.6}
    assert event["max_low_drawdowns"] == {"1": 0.0, "5": -0.1}


def test_load_decision_outcome_read_model_rows_rejects_execution_enabled_artifact(tmp_path):
    payload = _outcome_payload()
    payload["auto_trade_enabled"] = True
    json_path = tmp_path / "operator_decision_outcome_review_2026-05-01_2026-05-30.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="auto_trade_not_allowed"):
        load_decision_outcome_read_model_rows(json_path)


def test_import_decision_outcome_review_upserts_run_and_events(monkeypatch, tmp_path):
    from stock_research.operator_decision import outcome_read_model

    json_path = tmp_path / "operator_decision_outcome_review_2026-05-01_2026-05-30.json"
    json_path.write_text(json.dumps(_outcome_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(outcome_read_model, "connect", lambda service: _Context(conn))

    result = import_decision_outcome_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["run_ids"] == ["p8-outcome-2026-05-01-2026-05-30"]
    assert result["event_count"] == 1
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_decision_outcome_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    event_sql, event_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_decision_outcome_event" in event_sql
    assert "ON CONFLICT (outcome_event_id)" in event_sql
    assert event_params["decision_event_id"] == "operator_decision:morning-review:0:aaa"
    assert event_params["source_artifact_path"].endswith("operator_decision_journal_2026-05-30_morning-review.json")


def test_import_decision_outcome_review_accepts_directory(monkeypatch, tmp_path):
    from stock_research.operator_decision import outcome_read_model

    first = _outcome_payload()
    second = {
        **_outcome_payload(),
        "run_id": "p8-outcome-2026-05-31-2026-05-31",
        "review_start_date": "2026-05-31",
        "review_end_date": "2026-05-31",
    }
    (tmp_path / "operator_decision_outcome_review_2026-05-01_2026-05-30.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "operator_decision_outcome_review_2026-05-31_2026-05-31.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(outcome_read_model, "connect", lambda service: _Context(conn))

    result = import_decision_outcome_review(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["run_ids"] == [
        "p8-outcome-2026-05-01-2026-05-30",
        "p8-outcome-2026-05-31-2026-05-31",
    ]
    assert result["event_count"] == 2
