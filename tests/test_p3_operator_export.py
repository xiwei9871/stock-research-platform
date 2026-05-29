import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.p3 import operator_export


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_export_operator_review_writes_dashboard_ready_json_csv_and_manifest(
    tmp_path,
    monkeypatch,
):
    conn = object()
    calls = []

    def fake_fetch_all(opened, sql, params):
        assert opened is conn
        calls.append((sql, params))
        if "FROM ops.p2_review_run r" in sql and "DISTINCT ON" not in sql:
            return [
                {
                    "trade_date": "2026-05-29",
                    "run_id": "p2-smoke-2026-05-29",
                    "run_status": "manual_review_required",
                    "blocker_count": 1,
                    "warning_count": 2,
                    "json_path": "outputs/p2/aggregate/p2_aggregate_review.json",
                    "markdown_path": "outputs/p2/aggregate/p2_aggregate_review.md",
                }
            ]
        if "FROM ops.p2_review_section s" in sql:
            return [
                {
                    "trade_date": "2026-05-29",
                    "run_id": "p2-smoke-2026-05-29",
                    "section_group": "simulation",
                    "section_name": "virtual_portfolio",
                    "section_status": "warning",
                    "required": True,
                    "exists": True,
                    "source_artifact_path": "outputs/p2/simulation/review.json",
                }
            ]
        if "FROM simulation.virtual_portfolio_state_daily v" in sql:
            return [
                {
                    "trade_date": "2026-05-29",
                    "portfolio_id": "p2_smoke_demo",
                    "strategy_id": "p2_smoke:demo",
                    "review_status": "manual_review_required",
                    "risk_level": "warning",
                    "drawdown": -0.11,
                    "exposure_pct": 0.61,
                    "open_position_count": 1,
                    "source_artifact_path": "outputs/p2/inputs/portfolio_state.json",
                }
            ]
        if "DISTINCT ON (r.trade_date)" in sql:
            return [
                {
                    "trade_date": "2026-05-29",
                    "run_id": "p2-smoke-2026-05-29",
                    "run_status": "manual_review_required",
                    "blocker_count": 1,
                    "warning_count": 2,
                    "json_path": "outputs/p2/aggregate/p2_aggregate_review.json",
                    "markdown_path": "outputs/p2/aggregate/p2_aggregate_review.md",
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(
        operator_export,
        "connect",
        lambda service: _ConnectionContext(conn),
    )
    monkeypatch.setattr(operator_export, "fetch_all", fake_fetch_all)

    result = operator_export.export_operator_review(
        start_date="2026-05-29",
        end_date="2026-05-29",
        output_dir=tmp_path,
        status="manual_review_required",
        section_group="simulation",
        portfolio_id="p2_smoke_demo",
        service="stock_research_test",
    )

    assert result["row_counts"] == {
        "review_runs": 1,
        "review_sections": 1,
        "portfolio_risk": 1,
        "latest_status_by_trade_date": 1,
    }
    assert Path(result["manifest_path"]) == tmp_path / "manifest.json"
    assert pd.read_csv(tmp_path / "review_runs.csv").iloc[0]["blocker_count"] == 1
    portfolio_json = json.loads((tmp_path / "portfolio_risk.json").read_text())
    assert portfolio_json[0]["portfolio_id"] == "p2_smoke_demo"
    assert portfolio_json[0]["risk_level"] == "warning"
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["filters"] == {
        "start_date": "2026-05-29",
        "end_date": "2026-05-29",
        "status": "manual_review_required",
        "section_group": "simulation",
        "portfolio_id": "p2_smoke_demo",
    }
    assert "r.trade_date BETWEEN %s AND %s" in calls[0][0]
    assert "r.status = %s" in calls[0][0]
    assert calls[0][1] == [
        "2026-05-29",
        "2026-05-29",
        "manual_review_required",
    ]
    assert "s.section_group = %s" in calls[1][0]
    assert calls[1][1][-1] == "simulation"
    assert "v.portfolio_id = %s" in calls[2][0]
    assert calls[2][1][-1] == "p2_smoke_demo"


def test_export_operator_review_rejects_invalid_date_window(tmp_path):
    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        operator_export.export_operator_review(
            start_date="2026-05-30",
            end_date="2026-05-29",
            output_dir=tmp_path,
        )
