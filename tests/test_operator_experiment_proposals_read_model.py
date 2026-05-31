import json

import pytest

from stock_research.operator_decision.experiment_proposals_read_model import (
    import_experiment_proposal_review,
    load_experiment_proposal_read_model_rows,
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


def _proposal_payload() -> dict:
    return {
        "run_id": "p10-proposals-2026-05-31",
        "review_date": "2026-05-31",
        "status": "proposal_review_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "promotion_enabled": False,
        "proposal_count": 1,
        "status_counts": {"approved_for_experiment": 1},
        "proposals": [
            {
                "proposal_id": "p10-proposal:001",
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
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ],
    }


def test_load_experiment_proposal_rows_preserves_source_evidence_and_paths(tmp_path):
    json_path = tmp_path / "operator_experiment_proposals_2026-05-31.json"
    json_path.write_text(json.dumps(_proposal_payload()), encoding="utf-8")

    rows = load_experiment_proposal_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p10-proposals-2026-05-31"
    assert rows["run"]["review_date"] == "2026-05-31"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["proposals_csv_path"].endswith("_proposals.csv")
    assert rows["run"]["manual_review_required"] is True
    assert rows["run"]["auto_trade_enabled"] is False
    assert rows["run"]["promotion_enabled"] is False

    proposal = rows["proposals"][0]
    assert proposal["proposal_id"] == "p10-proposal:001"
    assert proposal["run_id"] == "p10-proposals-2026-05-31"
    assert proposal["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert proposal["source_analytics_group_ids"] == ["decision_label:candidate"]
    assert proposal["source_diagnostic_refs"] == ["top_forward_return:5:decision_label:candidate"]
    assert proposal["source_artifact_paths"] == ["outputs/p9/analytics.json"]
    assert proposal["proposal_artifact_path"] == str(json_path)
    assert proposal["promotion_enabled"] is False


def test_load_experiment_proposal_rows_rejects_execution_enabled_artifact(tmp_path):
    payload = _proposal_payload()
    payload["auto_trade_enabled"] = True
    json_path = tmp_path / "operator_experiment_proposals_2026-05-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="auto_trade_not_allowed"):
        load_experiment_proposal_read_model_rows(json_path)


def test_import_experiment_proposal_review_upserts_run_and_proposals(monkeypatch, tmp_path):
    from stock_research.operator_decision import experiment_proposals_read_model

    json_path = tmp_path / "operator_experiment_proposals_2026-05-31.json"
    json_path.write_text(json.dumps(_proposal_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(experiment_proposals_read_model, "connect", lambda service: _Context(conn))

    result = import_experiment_proposal_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["proposal_count"] == 1
    assert result["run_ids"] == ["p10-proposals-2026-05-31"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_experiment_proposal_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    proposal_sql, proposal_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_experiment_proposal" in proposal_sql
    assert "ON CONFLICT (proposal_id)" in proposal_sql
    assert proposal_params["proposal_id"] == "p10-proposal:001"
    assert proposal_params["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"


def test_import_experiment_proposal_review_accepts_directory(monkeypatch, tmp_path):
    from stock_research.operator_decision import experiment_proposals_read_model

    first = _proposal_payload()
    second = {
        **_proposal_payload(),
        "run_id": "p10-proposals-2026-06-01",
        "review_date": "2026-06-01",
    }
    (tmp_path / "operator_experiment_proposals_2026-05-31.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "operator_experiment_proposals_2026-06-01.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(experiment_proposals_read_model, "connect", lambda service: _Context(conn))

    result = import_experiment_proposal_review(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["proposal_count"] == 2
    assert result["run_ids"] == ["p10-proposals-2026-05-31", "p10-proposals-2026-06-01"]
