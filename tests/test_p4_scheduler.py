import json
from pathlib import Path

from stock_research.p4 import scheduler


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_run_daily_orchestration_imports_read_models_and_writes_operator_export(
    tmp_path,
    monkeypatch,
):
    calls = []
    aggregate_path = tmp_path / "p2_aggregate_review_2026-05-29.json"
    virtual_path = tmp_path / "virtual_portfolio_review_2026-05-29_demo.json"
    output_dir = tmp_path / "operator"
    aggregate_path.write_text("{}", encoding="utf-8")
    virtual_path.write_text("{}", encoding="utf-8")

    def fake_import_p2(path, *, service):
        calls.append(("p2", path, service))
        return {"imported_count": 1, "run_ids": ["p2-smoke-2026-05-29"]}

    def fake_import_virtual(path, *, service):
        calls.append(("virtual", path, service))
        return {
            "imported_count": 1,
            "state_count": 2,
            "position_count": 1,
            "portfolio_ids": ["p2_smoke_demo"],
        }

    def fake_export(**kwargs):
        calls.append(("export", kwargs))
        return {
            "manifest_path": str(output_dir / "manifest.json"),
            "row_counts": {
                "review_runs": 1,
                "review_sections": 2,
                "portfolio_risk": 1,
                "latest_status_by_trade_date": 1,
            },
            "files": {"review_runs": str(output_dir / "review_runs.csv")},
            "json_files": {"review_runs": str(output_dir / "review_runs.json")},
        }

    monkeypatch.setattr(scheduler, "import_p2_aggregate_review", fake_import_p2)
    monkeypatch.setattr(scheduler, "import_virtual_portfolio_review", fake_import_virtual)
    monkeypatch.setattr(scheduler, "export_operator_review", fake_export)

    result = scheduler.run_daily_orchestration(
        trade_date="2026-05-29",
        aggregate_review_path=aggregate_path,
        virtual_portfolio_path=virtual_path,
        output_dir=output_dir,
        portfolio_id="p2_smoke_demo",
        service="stock_research_test",
    )

    assert result["status"] == "ok"
    assert result["trade_date"] == "2026-05-29"
    assert result["blocker_count"] == 0
    assert result["p2_review_import"]["run_ids"] == ["p2-smoke-2026-05-29"]
    assert result["virtual_portfolio_import"]["state_count"] == 2
    assert result["operator_export"]["manifest_path"].endswith("manifest.json")
    assert calls[0] == ("p2", aggregate_path, "stock_research_test")
    assert calls[1] == ("virtual", virtual_path, "stock_research_test")
    assert calls[2][1]["start_date"] == "2026-05-29"
    assert calls[2][1]["end_date"] == "2026-05-29"
    assert calls[2][1]["portfolio_id"] == "p2_smoke_demo"


def test_run_daily_orchestration_reports_missing_artifacts_without_importing(
    tmp_path,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        scheduler,
        "import_p2_aggregate_review",
        lambda *args, **kwargs: calls.append("p2"),
    )
    monkeypatch.setattr(
        scheduler,
        "import_virtual_portfolio_review",
        lambda *args, **kwargs: calls.append("virtual"),
    )
    monkeypatch.setattr(
        scheduler,
        "export_operator_review",
        lambda *args, **kwargs: calls.append("export"),
    )

    result = scheduler.run_daily_orchestration(
        trade_date="2026-05-29",
        aggregate_review_path=tmp_path / "missing_aggregate.json",
        virtual_portfolio_path=tmp_path / "missing_virtual.json",
        output_dir=tmp_path / "operator",
    )

    assert result["status"] == "blocked"
    assert result["blocker_count"] == 2
    assert result["missing_artifacts"] == [
        str(tmp_path / "missing_aggregate.json"),
        str(tmp_path / "missing_virtual.json"),
    ]
    assert result["operator_export"] is None
    assert calls == []


def test_format_daily_orchestration_lines_is_machine_readable(tmp_path):
    result = {
        "status": "ok",
        "trade_date": "2026-05-29",
        "blocker_count": 0,
        "missing_artifacts": [],
        "p2_review_import": {"imported_count": 1},
        "virtual_portfolio_import": {"imported_count": 1, "state_count": 2, "position_count": 1},
        "operator_export": {
            "manifest_path": str(tmp_path / "manifest.json"),
            "row_counts": {"review_runs": 1, "portfolio_risk": 2},
        },
    }

    assert scheduler.format_daily_orchestration_lines(result) == [
        "p4_daily_orchestration|status|ok|trade_date|2026-05-29|blockers|0",
        "p4_daily_orchestration|p2_review_import|imported|1",
        "p4_daily_orchestration|virtual_portfolio_import|imported|1|states|2|positions|1",
        f"p4_daily_orchestration|operator_export|manifest|{tmp_path / 'manifest.json'}",
        "p4_daily_orchestration_dataset|portfolio_risk|rows|2",
        "p4_daily_orchestration_dataset|review_runs|rows|1",
    ]


def test_check_read_model_freshness_passes_for_current_rows_and_export_files(
    tmp_path,
    monkeypatch,
):
    review_csv = tmp_path / "review_runs.csv"
    review_json = tmp_path / "review_runs.json"
    review_csv.write_text("trade_date\n2026-05-29\n", encoding="utf-8")
    review_json.write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "row_counts": {"review_runs": 1, "portfolio_risk": 1},
                "files": {"review_runs": str(review_csv)},
                "json_files": {"review_runs": str(review_json)},
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch_all(conn, sql, params=None):
        if "FROM ops.p2_review_run" in sql:
            return [{"trade_date": "2026-05-29", "run_id": "p2-smoke"}]
        if "FROM simulation.virtual_portfolio_state_daily" in sql:
            return [{"trade_date": "2026-05-29", "portfolio_id": "p2_smoke_demo"}]
        raise AssertionError(sql)

    monkeypatch.setattr(scheduler, "connect", lambda service: _Context(object()))
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)

    result = scheduler.check_read_model_freshness(
        trade_date="2026-05-29",
        operator_manifest_path=manifest_path,
        portfolio_id="p2_smoke_demo",
        service="stock_research_test",
    )

    assert result["status"] == "pass"
    assert result["blocker_count"] == 0
    assert result["warning_count"] == 0
    assert result["checks"]["p2_review_run"]["status"] == "pass"
    assert result["checks"]["virtual_portfolio_state"]["status"] == "pass"
    assert result["checks"]["operator_export_files"]["status"] == "pass"
    assert result["checks"]["operator_export_row_counts"]["status"] == "pass"


def test_check_read_model_freshness_blocks_stale_rows_and_missing_files(
    tmp_path,
    monkeypatch,
):
    missing_csv = tmp_path / "missing.csv"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "row_counts": {"review_runs": 0},
                "files": {"review_runs": str(missing_csv)},
                "json_files": {},
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch_all(conn, sql, params=None):
        if "FROM ops.p2_review_run" in sql:
            return [{"trade_date": "2026-05-28", "run_id": "p2-old"}]
        if "FROM simulation.virtual_portfolio_state_daily" in sql:
            return []
        raise AssertionError(sql)

    monkeypatch.setattr(scheduler, "connect", lambda service: _Context(object()))
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)

    result = scheduler.check_read_model_freshness(
        trade_date="2026-05-29",
        operator_manifest_path=manifest_path,
        service="stock_research_test",
    )

    assert result["status"] == "blocked"
    assert result["blocker_count"] == 3
    assert result["warning_count"] == 1
    assert result["checks"]["p2_review_run"]["status"] == "blocked"
    assert result["checks"]["virtual_portfolio_state"]["status"] == "blocked"
    assert result["checks"]["operator_export_files"]["missing_files"] == [str(missing_csv)]
    assert result["checks"]["operator_export_row_counts"]["zero_count_datasets"] == ["review_runs"]


def test_format_read_model_freshness_lines_is_machine_readable():
    result = {
        "status": "blocked",
        "trade_date": "2026-05-29",
        "blocker_count": 1,
        "warning_count": 1,
        "checks": {
            "p2_review_run": {"status": "blocked", "latest_trade_date": "2026-05-28"},
            "operator_export_row_counts": {
                "status": "warning",
                "zero_count_datasets": ["review_runs"],
            },
        },
    }

    assert scheduler.format_read_model_freshness_lines(result) == [
        "p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|1",
        "p4_read_model_smoke_check|operator_export_row_counts|warning|zero_count_datasets|review_runs",
        "p4_read_model_smoke_check|p2_review_run|blocked|latest_trade_date|2026-05-28",
    ]
