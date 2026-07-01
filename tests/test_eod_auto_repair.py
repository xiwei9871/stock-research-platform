import json
from types import SimpleNamespace

from stock_research.eod_auto_repair import build_default_action_registry, run_eod_auto_repair
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairStatus


def test_run_eod_auto_repair_runs_action_for_failed_check_then_rechecks():
    calls = []
    check_results = [
        RepairCheckResult("lhb_features", RepairStatus.FAILED, "missing", blocker=True),
        RepairCheckResult("lhb_features", RepairStatus.SUCCESS, "ready"),
    ]

    def check_plan_builder(trade_date):
        def run_check():
            calls.append("check")
            return check_results.pop(0)

        return [SimpleNamespace(name="lhb_features", run=run_check)]

    def action_runner(trade_date, output_dir):
        calls.append("repair_lhb")
        return RepairActionResult("repair_lhb_source_and_features", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir="/tmp/out",
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"lhb_features": action_runner},
    )

    assert calls == ["check", "repair_lhb", "check"]
    assert summary.final_status == RepairStatus.SUCCESS
    assert summary.actions[0].name == "repair_lhb_source_and_features"


def test_run_eod_auto_repair_check_mode_does_not_run_actions():
    calls = []

    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True)

        return [SimpleNamespace(name="strategy_publish", run=run_check)]

    def action_runner(trade_date, output_dir):
        calls.append("repair")
        return RepairActionResult("publish_strategy_eod", RepairStatus.SUCCESS)

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir="/tmp/out",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": action_runner},
    )

    assert calls == []
    assert summary.final_status == RepairStatus.FAILED


def test_run_eod_auto_repair_treats_skipped_checks_as_degraded():
    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("minute5_bars", RepairStatus.SKIPPED, "check runner not wired")

        return [SimpleNamespace(name="minute5_bars", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir="/tmp/out",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    assert summary.final_status == RepairStatus.DEGRADED


def test_run_eod_auto_repair_writes_json_and_markdown_report(tmp_path):
    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("review_queue", RepairStatus.SUCCESS, "ready", metrics={"row_count": 14})

        return [SimpleNamespace(name="review_queue", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    payload = json.loads((tmp_path / "run_summary.json").read_text())
    report = (tmp_path / "run_report.md").read_text()
    assert payload["trade_date"] == "2026-06-29"
    assert summary.final_status == RepairStatus.SUCCESS
    assert "review_queue" in report
    assert "row_count" in report


def test_default_action_registry_contains_repairable_checks():
    registry = build_default_action_registry(output_root="outputs")

    assert "minute5_bars" in registry
    assert "lhb_features" in registry
    assert "strategy_publish" in registry
    assert "market_monitor" in registry
