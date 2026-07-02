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


def test_run_eod_auto_repair_degraded_non_blocker_is_not_remaining_issue(tmp_path):
    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("reports", RepairStatus.DEGRADED, "ready with warnings")

        return [SimpleNamespace(name="reports", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    assert summary.final_status == RepairStatus.DEGRADED
    assert summary.remaining_blockers == []
    assert summary.remaining_non_blockers == []
    assert summary.next_actions == []


def test_run_eod_auto_repair_next_actions_include_blockers_and_non_blocking_gaps(tmp_path):
    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="reports",
                run=lambda: RepairCheckResult("reports", RepairStatus.FAILED, "missing", blocker=False),
            ),
        ]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    assert summary.remaining_blockers == ["strategy_publish"]
    assert summary.remaining_non_blockers == ["reports"]
    assert summary.next_actions == [
        "Resolve blocking checks: strategy_publish",
        "Review non-blocking gaps: reports",
    ]


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


def test_run_eod_auto_repair_records_action_exception_and_writes_report(tmp_path):
    def check_plan_builder(trade_date):
        results = [
            RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            RepairCheckResult("strategy_publish", RepairStatus.FAILED, "still missing", blocker=True),
        ]

        def run_check():
            return results.pop(0)

        return [SimpleNamespace(name="strategy_publish", run=run_check)]

    def broken_action(trade_date, output_dir):
        raise RuntimeError("base data checks did not all pass")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": broken_action},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.actions[0].status == RepairStatus.FAILED
    assert "RuntimeError" in summary.actions[0].message
    assert summary.remaining_blockers == ["strategy_publish"]
    assert summary.next_actions == ["Resolve blocking checks: strategy_publish"]
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()


def test_run_eod_auto_repair_writes_report_when_check_raises(tmp_path):
    def check_plan_builder(trade_date):
        def run_check():
            raise RuntimeError("database unavailable")

        return [SimpleNamespace(name="daily_bars", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.checks_before[0].name == "daily_bars"
    assert summary.checks_before[0].blocker is True
    assert "RuntimeError" in summary.checks_before[0].message
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()


def test_run_eod_auto_repair_writes_report_when_check_plan_builder_raises(tmp_path):
    def check_plan_builder(trade_date):
        raise RuntimeError("plan unavailable")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.checks_before[0].name == "check_plan"
    assert summary.checks_before[0].blocker is True
    assert "RuntimeError" in summary.checks_before[0].message
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()


def test_run_eod_auto_repair_writes_report_when_recheck_plan_builder_raises(tmp_path):
    calls = {"plans": 0}

    def check_plan_builder(trade_date):
        calls["plans"] += 1
        if calls["plans"] == 2:
            raise RuntimeError("recheck unavailable")
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            )
        ]

    def action_runner(trade_date, output_dir):
        return RepairActionResult("repair_strategy_publish", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": action_runner},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.actions[0].status == RepairStatus.SUCCESS
    assert summary.checks_after[0].name == "check_plan"
    assert "RuntimeError" in summary.checks_after[0].message
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()
