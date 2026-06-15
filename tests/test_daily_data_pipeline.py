import json
from pathlib import Path

from stock_research.daily_data_pipeline import (
    DailyPipelineStep,
    build_daily_pipeline_steps,
    derive_daily_windows,
    render_daily_pipeline_feishu_message,
    run_stock_daily_data_pipeline,
)


def test_derive_daily_windows_uses_short_daily_lookbacks() -> None:
    windows = derive_daily_windows("2026-06-05")

    assert windows["trade_date"] == "2026-06-05"
    assert windows["market_start_date"] == "2026-05-31"
    assert windows["minute_start_date"] == "2026-05-31"
    assert windows["lhb_start_date"] == "2026-05-26"
    assert windows["announcement_start_date"] == "2026-05-22"
    assert windows["earnings_start_date"] == "2026-04-21"
    assert windows["repurchase_start_date"] == "2026-03-07"


def test_build_daily_pipeline_steps_lists_required_initial_steps() -> None:
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    assert [step.name for step in steps] == [
        "start_report",
        "sync_core_assets",
        "load_market_bars",
        "check_market_data_freshness",
        "build_asset_status",
        "sync_index_bars",
        "sync_index_constituents",
        "sync_industry_memberships",
        "build_industry_bars",
        "minute_incremental_refresh",
        "daily_event_refresh",
        "daily_feature_build",
        "label_incremental_refresh",
        "daily_report_delivery",
    ]
    assert all(isinstance(step, DailyPipelineStep) for step in steps)
    assert steps[0].required is False
    assert next(step for step in steps if step.name == "sync_core_assets").required is True
    assert next(step for step in steps if step.name == "label_incremental_refresh").required is False


def test_build_daily_pipeline_steps_splits_market_refresh_commands() -> None:
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    incremental_steps = [
        step for step in steps if "run-daily-incremental" in step.command
    ]

    assert [step.name for step in incremental_steps] == [
        "sync_core_assets",
        "load_market_bars",
        "check_market_data_freshness",
        "build_asset_status",
        "sync_index_bars",
        "sync_index_constituents",
        "sync_industry_memberships",
        "build_industry_bars",
        "label_incremental_refresh",
    ]
    for step in incremental_steps:
        assert "--only-step" in step.command
    assert "--label-start-date" in incremental_steps[-1].command
    assert "2026-03-07" in incremental_steps[-1].command


def test_build_daily_pipeline_steps_commands_parse_through_cli() -> None:
    from stock_research.cli import build_parser

    parser = build_parser()
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    for step in steps:
        if step.command:
            assert step.command[0] == "/Users/xiwei/stock_research/.venv/bin/python"
            parser.parse_args(step.command[3:])


def test_render_daily_pipeline_feishu_message_is_mobile_sized() -> None:
    message = render_daily_pipeline_feishu_message(
        trade_date="2026-06-05",
        status="partial_failed",
        output_dir=Path("outputs/daily/20260605"),
        step_results=[
            {"step": "market_daily_refresh", "status": "success", "rows": 5200, "error": ""},
            {"step": "daily_event_refresh", "status": "partial_failed", "rows": 45, "error": "lhb failed"},
        ],
    )

    assert "A股日频数据任务" in message
    assert "2026-06-05" in message
    assert "market_daily_refresh: success rows=5200" in message
    assert "daily_event_refresh: partial_failed rows=45 error=lhb failed" in message
    assert "outputs/daily/20260605" in message
    assert len(message) < 1800


def test_run_stock_daily_data_pipeline_records_success_and_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        calls.append(command)
        if "free-enrichment-backfill" in command:
            return {"returncode": 1, "stdout": "failed output", "stderr": "lhb failed"}
        return {"returncode": 0, "stdout": "rows|12", "stderr": ""}

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    assert result["status"] == "partial_failed"
    assert len(result["steps"]) == 14
    assert any(
        step["step"] == "daily_event_refresh" and step["status"] == "failed"
        for step in result["steps"]
    )
    assert calls
    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["trade_date"] == "2026-06-05"
    assert summary["status"] == "PARTIAL"
    assert summary["legacy_status"] == "partial_failed"


def test_run_stock_daily_data_pipeline_can_skip_feishu(tmp_path: Path) -> None:
    sent: list[str] = []

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
        feishu_sender=lambda message: sent.append(message),
        send_feishu=False,
    )

    assert result["status"] == "success"
    assert sent == []


def test_run_stock_daily_data_pipeline_skips_commands_after_required_failure(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        calls.append(command)
        if "load_market_bars" in command:
            return {"returncode": 1, "stdout": "", "stderr": "market failed"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    assert result["status"] == "partial_failed"
    assert len(calls) == 2
    assert "load_market_bars" in calls[-1]

    steps = {step["step"]: step for step in result["steps"]}
    for step_name in [
        "check_market_data_freshness",
        "build_asset_status",
        "sync_index_bars",
        "sync_index_constituents",
        "sync_industry_memberships",
        "build_industry_bars",
        "minute_incremental_refresh",
        "daily_event_refresh",
        "daily_feature_build",
        "label_incremental_refresh",
    ]:
        assert steps[step_name]["status"] == "skipped_dependency_failed"
        assert steps[step_name]["rows"] == 0
        assert steps[step_name]["error"] == "upstream required step failed"


def test_run_stock_daily_data_pipeline_keeps_optional_label_failure_nonblocking(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        calls.append(command)
        if "compute_labels" in command:
            return {"returncode": 1, "stdout": "", "stderr": "label timed out"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    assert result["status"] == "success"
    steps = {step["step"]: step for step in result["steps"]}
    assert steps["label_incremental_refresh"]["status"] == "failed"
    assert steps["daily_feature_build"]["status"] == "success"
    assert any("run-daily-factor-pipeline" in command for command in calls)


def test_run_stock_daily_data_pipeline_writes_step_logs(tmp_path: Path) -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        return {
            "returncode": 0,
            "stdout": "rows|7\nstdout detail",
            "stderr": "stderr detail",
        }

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    first_command_step = next(step for step in result["steps"] if step["step"] == "sync_core_assets")
    log_path = Path(first_command_step["log_path"])
    assert log_path.exists()
    log_text = log_path.read_text()
    assert "command:" in log_text
    assert "stdout detail" in log_text
    assert "stderr detail" in log_text


def test_run_stock_daily_data_pipeline_writes_v2_summary_and_manifest(tmp_path: Path) -> None:
    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {
            "returncode": 0,
            "stdout": "rows|12",
            "stderr": "",
        },
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    manifest_payload = json.loads((tmp_path / "run_manifest.json").read_text())

    assert result["run_id"] == "eod-2026-06-05-local"
    assert summary["run_id"] == "eod-2026-06-05-local"
    assert summary["run_date"]
    assert summary["latest_market_date"] == "2026-06-05"
    assert summary["status"] == "OK"
    assert summary["tier1_status"] == "OK"
    assert summary["tier2_status"] == "OK"
    assert "modules" in summary
    assert "steps" in summary
    assert summary["topn_generated"] is True
    assert summary["topn_count"] == 12
    assert summary["review_queue_count"] == 12
    assert summary["readiness_status"] == summary["status"]
    assert summary["dashboard_readiness_url"].endswith("/api/platform/readiness")
    assert manifest_payload["run_id"] == summary["run_id"]
    assert {item["module"] for item in manifest_payload["modules"]} >= {
        "assets_universe",
        "daily_bars",
        "factor_pipeline",
        "score_topn",
        "review_queue",
        "news",
        "research_reports",
        "minute_bars",
    }


def test_run_stock_daily_data_pipeline_tier1_failure_blocks_summary(tmp_path: Path) -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        if "load_market_bars" in command:
            return {"returncode": 1, "stdout": "", "stderr": "market failed"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["status"] == "BLOCKED"
    assert summary["tier1_status"] == "BLOCKED"
    assert "daily_bars" in summary["missing_data"]
    assert any("market failed" in error for error in summary["errors"])


def test_run_stock_daily_data_pipeline_tier2_failure_is_partial(tmp_path: Path) -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        if "free-enrichment-backfill" in command:
            return {"returncode": 1, "stdout": "", "stderr": "lhb failed"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["status"] == "PARTIAL"
    assert summary["tier1_status"] == "OK"
    assert summary["tier2_status"] == "PARTIAL"
    assert "lhb" in summary["partial_data"]


def test_run_stock_daily_data_pipeline_records_successful_feishu_delivery(
    tmp_path: Path,
) -> None:
    sent: list[str] = []

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {
            "returncode": 0,
            "stdout": "rows|3",
            "stderr": "",
        },
        feishu_sender=lambda message: sent.append(message),
        send_feishu=True,
    )

    assert result["status"] == "success"
    assert len(sent) == 1
    delivery = next(step for step in result["steps"] if step["step"] == "daily_report_delivery")
    assert delivery["status"] == "success"

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    summary_delivery = next(
        step for step in summary["steps"] if step["step"] == "daily_report_delivery"
    )
    assert summary_delivery["status"] == "success"
    assert "daily_report_delivery: success" in (tmp_path / "feishu_message.txt").read_text()


def test_run_stock_daily_data_pipeline_records_failed_feishu_delivery(
    tmp_path: Path,
) -> None:
    def failing_sender(message: str) -> None:
        raise RuntimeError("feishu unavailable")

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {
            "returncode": 0,
            "stdout": "rows|3",
            "stderr": "",
        },
        feishu_sender=failing_sender,
        send_feishu=True,
    )

    assert result["status"] == "partial_failed"
    delivery = next(step for step in result["steps"] if step["step"] == "daily_report_delivery")
    assert delivery["status"] == "failed"
    assert delivery["error"] == "feishu unavailable"

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    summary_delivery = next(
        step for step in summary["steps"] if step["step"] == "daily_report_delivery"
    )
    assert summary["status"] == "PARTIAL"
    assert summary["legacy_status"] == "partial_failed"
    assert summary_delivery["status"] == "failed"
    assert summary_delivery["error"] == "feishu unavailable"
    assert "daily_report_delivery: failed" in (tmp_path / "feishu_message.txt").read_text()
    assert "feishu unavailable" in (tmp_path / "feishu_message.txt").read_text()
