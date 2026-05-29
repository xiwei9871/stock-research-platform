import json
from pathlib import Path

from stock_research.p2.review_read_model import (
    import_p2_aggregate_review,
    load_p2_aggregate_review_rows,
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


def _review_payload() -> dict:
    return {
        "trade_date": "2026-05-29",
        "run_id": "p2-smoke-2026-05-29",
        "status": "review_required",
        "source_rollup_status": "ready",
        "blocker_count": 0,
        "warning_count": 1,
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
        "sections": [
            {
                "group": "simulation",
                "name": "virtual_portfolio_review",
                "status": "manual_review_required",
                "required": True,
                "exists": True,
                "path": "outputs/p2/simulation/virtual_portfolio_review.json",
                "summary": {"latest_risk_level": "warning", "max_drawdown": -0.11},
            },
            {
                "group": "agent",
                "name": "agent_report",
                "status": "passed",
                "required": True,
                "exists": True,
                "path": "outputs/p2/agent/agent_report.json",
                "summary": {"blocker_count": 0},
            },
        ],
    }


def test_load_p2_aggregate_review_rows_preserves_run_and_section_paths(tmp_path):
    json_path = tmp_path / "p2_aggregate_review_2026-05-29.json"
    markdown_path = tmp_path / "p2_aggregate_review_2026-05-29.md"
    json_path.write_text(json.dumps(_review_payload()), encoding="utf-8")
    markdown_path.write_text("# P2 Aggregate Review\n", encoding="utf-8")

    rows = load_p2_aggregate_review_rows(json_path)

    assert rows["run"]["run_id"] == "p2-smoke-2026-05-29"
    assert rows["run"]["trade_date"] == "2026-05-29"
    assert rows["run"]["status"] == "review_required"
    assert rows["run"]["artifact_count"] == 2
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["markdown_path"] == str(markdown_path)
    assert rows["sections"][0]["section_group"] == "simulation"
    assert rows["sections"][0]["source_artifact_path"].endswith("virtual_portfolio_review.json")
    assert rows["sections"][0]["summary"]["latest_risk_level"] == "warning"


def test_import_p2_aggregate_review_upserts_run_and_sections(monkeypatch, tmp_path):
    from stock_research.p2 import review_read_model

    json_path = tmp_path / "p2_aggregate_review_2026-05-29.json"
    json_path.write_text(json.dumps(_review_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(review_read_model, "connect", lambda service: _Context(conn))

    result = import_p2_aggregate_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["run_ids"] == ["p2-smoke-2026-05-29"]
    assert len(conn.cursor_obj.calls) == 3
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.p2_review_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["run_id"] == "p2-smoke-2026-05-29"
    assert run_params["status"] == "review_required"
    assert run_params["metadata"] == '{"auto_trade_enabled": false, "human_confirmation_required": true}'
    section_sql, section_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.p2_review_section" in section_sql
    assert "ON CONFLICT (run_id, section_group, section_name)" in section_sql
    assert section_params["section_group"] == "simulation"
    assert '"latest_risk_level": "warning"' in section_params["summary"]


def test_import_p2_aggregate_review_accepts_directory(monkeypatch, tmp_path):
    from stock_research.p2 import review_read_model

    first = _review_payload()
    second = {
        **_review_payload(),
        "run_id": "p2-smoke-2026-05-30",
        "trade_date": "2026-05-30",
    }
    (tmp_path / "p2_aggregate_review_2026-05-29.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "p2_aggregate_review_2026-05-30.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(review_read_model, "connect", lambda service: _Context(conn))

    result = import_p2_aggregate_review(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["run_ids"] == ["p2-smoke-2026-05-29", "p2-smoke-2026-05-30"]
