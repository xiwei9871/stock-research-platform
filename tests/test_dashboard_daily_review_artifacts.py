import json
from pathlib import Path

from stock_research.dashboard import daily_review_lite
from stock_research.dashboard import daily_review_artifacts


def _payload():
    return {
        "trade_date": "2026-06-18",
        "status": "ready",
        "run": {"run_id": "", "source": "report_run", "report_type": "daily_review_lite", "status": "completed"},
        "fallback": False,
        "sections": [
            {"key": "data_readiness", "title": "Data Readiness", "status": "ready", "items": [{"label": "市场日期", "value": "2026-06-18"}]},
            {"key": "market_review", "title": "Market Review", "status": "ready", "items": [{"label": "上涨/下跌", "value": "1552 / 3380"}]},
            {"key": "strategy_summaries", "title": "Strategy Summaries", "status": "ready", "items": [{"label": "LHB", "value": "3 只"}]},
            {"key": "holding_review", "title": "Holding Review", "status": "partial", "items": []},
            {"key": "operator_plan", "title": "Operator Plan", "status": "empty", "items": []},
            {"key": "next_day_checklist", "title": "Next-day Checklist", "status": "empty", "items": []},
            {"key": "artifacts", "title": "Artifacts", "status": "empty", "items": []},
        ],
        "artifacts": [],
        "warnings": [],
    }


def test_write_daily_review_artifacts_writes_expected_files(tmp_path):
    paths = daily_review_artifacts.write_daily_review_artifacts(_payload(), tmp_path)

    expected = {
        "json_path",
        "markdown_path",
        "manifest_path",
        "operator_plan_template_path",
    }
    assert expected.issubset(paths.keys())
    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["manifest_path"]).exists()
    assert Path(paths["operator_plan_template_path"]).exists()

    manifest = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["trade_date"] == "2026-06-18"
    assert manifest["status"] == "ready"


def test_generate_and_register_run_records_daily_review_report(monkeypatch, tmp_path):
    record_calls = {}
    monkeypatch.setattr(daily_review_lite, "_build_live_daily_review_payload", lambda trade_date, service=None: _payload(), raising=False)
    monkeypatch.setattr(daily_review_lite, "DAILY_REVIEW_OUTPUT_ROOT", tmp_path, raising=False)

    def fake_record_report_run(**kwargs):
        record_calls.update(kwargs)
        return "daily_review_lite:2026-06-18:abc123"

    monkeypatch.setattr(daily_review_lite, "record_report_run", fake_record_report_run, raising=False)

    run = daily_review_lite._generate_and_register_run("2026-06-18")

    assert run["run_id"] == "daily_review_lite:2026-06-18:abc123"
    assert record_calls["trade_date"] == "2026-06-18"
    assert record_calls["report_type"] == "daily_review_lite"
    assert "daily_review_lite_2026-06-18.json" in record_calls["report_paths"]["json_path"]


def test_build_daily_review_lite_prefers_registered_json_and_generates_when_missing(monkeypatch, tmp_path):
    payload = _payload()
    paths = daily_review_artifacts.write_daily_review_artifacts(payload, tmp_path)
    generated_run = {
        "run_id": "daily_review_lite:2026-06-18:abc123",
        "trade_date": "2026-06-18",
        "report_type": "daily_review_lite",
        "status": "completed",
        "report_paths": paths,
        "metadata": {},
        "updated_at": "2026-06-22T12:00:00Z",
    }
    generate_calls = []

    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", lambda *args, **kwargs: None)

    def fake_generate(trade_date, service=None):
        generate_calls.append(trade_date)
        return generated_run

    monkeypatch.setattr(daily_review_lite, "_generate_and_register_run", fake_generate, raising=False)

    result = daily_review_lite.build_daily_review_lite("2026-06-18")

    assert generate_calls == ["2026-06-18"]
    assert result["status"] == "ready"
    assert result["run"]["source"] == "report_run"
    assert result["warnings"] == []
    assert result["trade_date"] == "2026-06-18"


def test_build_daily_review_lite_falls_back_when_artifact_directory_is_read_only(monkeypatch):
    monkeypatch.setattr(daily_review_lite, "_latest_registered_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(daily_review_lite, "load_platform_summary", lambda service=None: {"latest_market_date": "2026-06-18"}, raising=False)
    monkeypatch.setattr(daily_review_lite, "_build_live_daily_review_payload", lambda trade_date, service=None: _payload(), raising=False)

    def raise_read_only(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(daily_review_lite, "write_daily_review_artifacts", raise_read_only, raising=False)

    result = daily_review_lite.build_daily_review_lite("2026-06-18")

    assert result["trade_date"] == "2026-06-18"
    assert result["fallback"] is True
    assert result["run"]["source"] == "fallback"
    assert "no registered daily review run selected" in result["warnings"]


def test_load_payload_from_run_resolves_migrated_report_paths(monkeypatch, tmp_path):
    payload = _payload()
    reports_root = tmp_path / "reports"
    trade_dir = reports_root / "daily_review_lite" / "2026-06-18"
    paths = daily_review_artifacts.write_daily_review_artifacts(payload, trade_dir)
    migrated_paths = dict(paths)
    migrated_paths["json_path"] = "/nonexistent/legacy/reports/daily_review_lite/2026-06-18/daily_review_lite_2026-06-18.json"
    run = {
        "run_id": "daily_review_lite:2026-06-18:abc123",
        "trade_date": "2026-06-18",
        "report_type": "daily_review_lite",
        "status": "completed",
        "report_paths": migrated_paths,
        "metadata": {},
        "updated_at": "2026-06-22T12:00:00Z",
    }

    monkeypatch.setattr(daily_review_lite, "DAILY_REVIEW_OUTPUT_ROOT", reports_root / "daily_review_lite", raising=False)
    monkeypatch.setattr(daily_review_lite, "load_report_links", lambda trade_date: [], raising=False)

    result = daily_review_lite._load_payload_from_run(run, selected_trade_date="2026-06-18")

    assert result is not None
    assert result["trade_date"] == "2026-06-18"
    assert result["run"]["source"] == "report_run"
    assert result["fallback"] is False
