import json

import pytest

from stock_research.operator_decision.experiment_replay_read_model import (
    import_experiment_replay_review,
    load_experiment_replay_read_model_rows,
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


def _replay_payload() -> dict:
    return {
        "run_id": "p11-replay-run-2026-06-30",
        "replay_start_date": "2026-01-01",
        "replay_end_date": "2026-05-31",
        "status": "replay_review_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_write_enabled": False,
        "result_count": 1,
        "status_counts": {"passed_offline_replay": 1},
        "results": [
            {
                "replay_result_id": "p11-replay:001",
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
                "metric_summary": {"forward_5d_return_mean": 0.08, "win_rate": 0.75},
                "failure_reason": "",
                "defer_reason": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }


def test_load_experiment_replay_rows_preserves_sources_and_paths(tmp_path):
    json_path = tmp_path / "operator_experiment_replay_2026-01-01_2026-05-31.json"
    json_path.write_text(json.dumps(_replay_payload()), encoding="utf-8")

    rows = load_experiment_replay_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p11-replay-run-2026-06-30"
    assert rows["run"]["replay_start_date"] == "2026-01-01"
    assert rows["run"]["replay_end_date"] == "2026-05-31"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["results_csv_path"].endswith("_results.csv")
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False
    assert rows["run"]["production_write_enabled"] is False

    result = rows["results"][0]
    assert result["replay_result_id"] == "p11-replay:001"
    assert result["run_id"] == "p11-replay-run-2026-06-30"
    assert result["proposal_id"] == "p10-proposal:001"
    assert result["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert result["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert result["replay_input_artifact_paths"] == ["inputs/p11/replay_candidates.csv"]
    assert result["metric_summary"] == {"forward_5d_return_mean": 0.08, "win_rate": 0.75}
    assert result["replay_artifact_path"] == str(json_path)
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_write_enabled"] is False


def test_load_experiment_replay_rows_rejects_execution_enabled_artifact(tmp_path):
    payload = _replay_payload()
    payload["production_write_enabled"] = True
    json_path = tmp_path / "operator_experiment_replay_2026-01-01_2026-05-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_experiment_replay_read_model_rows(json_path)


def test_import_experiment_replay_review_upserts_run_and_results(monkeypatch, tmp_path):
    from stock_research.operator_decision import experiment_replay_read_model

    json_path = tmp_path / "operator_experiment_replay_2026-01-01_2026-05-31.json"
    json_path.write_text(json.dumps(_replay_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(experiment_replay_read_model, "connect", lambda service: _Context(conn))

    result = import_experiment_replay_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["result_count"] == 1
    assert result["run_ids"] == ["p11-replay-run-2026-06-30"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_experiment_replay_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    result_sql, result_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_experiment_replay_result" in result_sql
    assert "ON CONFLICT (replay_result_id)" in result_sql
    assert result_params["replay_result_id"] == "p11-replay:001"
    assert result_params["proposal_id"] == "p10-proposal:001"
    assert result_params["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"


def test_import_experiment_replay_review_accepts_directory(monkeypatch, tmp_path):
    from stock_research.operator_decision import experiment_replay_read_model

    first = _replay_payload()
    second = {
        **_replay_payload(),
        "run_id": "p11-replay-run-2026-07-31",
        "replay_end_date": "2026-07-31",
        "results": [
            {
                **_replay_payload()["results"][0],
                "replay_result_id": "p11-replay:002",
                "replay_end_date": "2026-07-31",
            }
        ],
    }
    (tmp_path / "operator_experiment_replay_2026-01-01_2026-05-31.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "operator_experiment_replay_2026-01-01_2026-07-31.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(experiment_replay_read_model, "connect", lambda service: _Context(conn))

    result = import_experiment_replay_review(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["result_count"] == 2
    assert result["run_ids"] == [
        "p11-replay-run-2026-06-30",
        "p11-replay-run-2026-07-31",
    ]
