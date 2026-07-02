import json
from types import SimpleNamespace

import pandas as pd

import stock_research.reports.daily_research_report_cli as daily_research_report_cli
import stock_research.strategy_eod_publish as strategy_eod_publish
import stock_research.watchlist.workflow as watchlist_workflow
from stock_research.data_run_manifest import build_manifest_entry
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
    assert "technical_features" in registry
    assert "lhb_features" in registry
    assert "score_topn" in registry
    assert "watchlist" in registry
    assert "market_monitor" in registry
    assert "strategy_publish" in registry
    assert "reports" in registry
    assert "review_evidence_snapshots" in registry


def test_default_watchlist_action_persists_diagnostics_snapshot(monkeypatch, tmp_path):
    stored = []

    monkeypatch.setattr(
        watchlist_workflow,
        "build_watchlist_snapshot",
        lambda **kwargs: pd.DataFrame(
            [{"watchlist_id": kwargs["watchlist_id"], "trade_date": kwargs["trade_date"], "asset_id": "A"}]
        ),
    )
    monkeypatch.setattr(
        watchlist_workflow,
        "build_watchlist_diagnostics_snapshot",
        lambda **kwargs: {
            "risk": pd.DataFrame(
                [{"watchlist_id": "diagnostics", "trade_date": kwargs["trade_date"], "asset_id": "B"}]
            )
        },
    )
    monkeypatch.setattr(
        watchlist_workflow,
        "store_watchlist_daily_signals",
        lambda frame: stored.append(frame.copy()) or len(frame),
    )

    result = build_default_action_registry(output_root="outputs")["watchlist"]("2026-07-01", tmp_path)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics == {"default_rows": 1, "diagnostics_rows": 1}
    assert len(stored) == 1
    assert stored[0]["watchlist_id"].tolist() == ["diagnostics"]


def test_default_reports_action_generates_daily_research_reports_before_manifest_refresh(monkeypatch, tmp_path):
    calls = []
    entries = [
        build_manifest_entry(
            run_id="run-1",
            run_date="2026-07-01",
            trade_date="2026-07-01",
            module="generated_reports",
            source="reports",
            tier="tier2",
            status="success",
            started_at="2026-07-01T00:00:00Z",
            ended_at="2026-07-01T00:00:01Z",
            row_count=2,
            asset_count=None,
            latest_trade_date="2026-07-01",
            artifact_path="/tmp/reports/bundle.md",
            metadata={"reports_dir": "/tmp/reports"},
        )
    ]

    def fake_run_daily_research_report(**kwargs):
        calls.append(("generate", kwargs))
        return {"report_paths": {"bundle": {"markdown_path": "/tmp/reports/bundle.md"}}}

    monkeypatch.setattr(daily_research_report_cli, "run_daily_research_report", fake_run_daily_research_report)
    monkeypatch.setattr(strategy_eod_publish, "_write_report_content_manifest_entries", lambda **kwargs: entries)
    monkeypatch.setattr("stock_research.data_run_manifest.upsert_data_run_manifest", lambda entry: calls.append(("upsert", entry)))

    result = build_default_action_registry(output_root="outputs")["reports"]("2026-07-01", tmp_path)

    assert calls[0][0] == "generate"
    assert calls[0][1]["trade_date"] == "2026-07-01"
    assert calls[0][1]["score_version"] == "manual_v1"
    assert calls[0][1]["record_run"] is False
    assert ("upsert", entries[0]) in calls
    assert result.metrics["generated_reports"] == 2
    assert result.artifact_paths == ["/tmp/reports"]


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


def test_run_eod_auto_repair_runs_stages_in_dependency_order(tmp_path):
    calls = []
    check_state = {
        "minute5_bars": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "score_topn": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "watchlist": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "strategy_publish": [RepairStatus.FAILED, RepairStatus.SUCCESS],
    }

    def check_plan_builder(trade_date):
        checks = []
        for name in ["minute5_bars", "score_topn", "watchlist", "strategy_publish"]:

            def run_check(check_name=name):
                status = check_state[check_name][0]
                return RepairCheckResult(
                    check_name,
                    status,
                    "ready" if status == RepairStatus.SUCCESS else "missing",
                    blocker=status == RepairStatus.FAILED,
                )

            checks.append(SimpleNamespace(name=name, run=run_check))
        return checks

    def make_action(name):
        def action(trade_date, output_dir):
            calls.append(name)
            check_name = {
                "repair_minute5_bars": "minute5_bars",
                "repair_score_topn": "score_topn",
                "repair_watchlist": "watchlist",
                "repair_strategy_publish": "strategy_publish",
            }[name]
            check_state[check_name].pop(0)
            return RepairActionResult(name, RepairStatus.SUCCESS, "fixed")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={
            "minute5_bars": make_action("repair_minute5_bars"),
            "score_topn": make_action("repair_score_topn"),
            "watchlist": make_action("repair_watchlist"),
            "strategy_publish": make_action("repair_strategy_publish"),
        },
    )

    assert calls == [
        "repair_minute5_bars",
        "repair_score_topn",
        "repair_watchlist",
        "repair_strategy_publish",
    ]
    assert summary.final_status == RepairStatus.SUCCESS
    assert [stage.name for stage in summary.stages] == [
        "base_bars",
        "scores_and_watchlists",
        "strategy_eod",
    ]


def test_run_eod_auto_repair_stops_downstream_stage_when_prerequisite_blocker_remains(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="minute5_bars",
                run=lambda: RepairCheckResult("minute5_bars", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="score_topn",
                run=lambda: RepairCheckResult("score_topn", RepairStatus.FAILED, "missing", blocker=True),
            ),
        ]

    def minute_action(trade_date, output_dir):
        calls.append("repair_minute5_bars")
        return RepairActionResult("repair_minute5_bars", RepairStatus.FAILED, "still missing")

    def score_action(trade_date, output_dir):
        calls.append("repair_score_topn")
        return RepairActionResult("repair_score_topn", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"minute5_bars": minute_action, "score_topn": score_action},
    )

    assert calls == ["repair_minute5_bars"]
    assert summary.final_status == RepairStatus.FAILED
    assert summary.remaining_blockers == ["minute5_bars", "score_topn"]


def test_run_eod_auto_repair_stage_results_are_scoped_to_stage_checks(tmp_path):
    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="minute5_bars",
                run=lambda: RepairCheckResult("minute5_bars", RepairStatus.SUCCESS, "ready"),
            ),
            SimpleNamespace(
                name="score_topn",
                run=lambda: RepairCheckResult("score_topn", RepairStatus.FAILED, "missing", blocker=True),
            ),
        ]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    assert [check.name for check in summary.stages[0].checks_after] == ["minute5_bars"]
    assert summary.stages[0].remaining_blockers == []


def test_run_eod_auto_repair_publish_only_skips_lower_level_repair_actions(tmp_path):
    calls = []
    strategy_status = [RepairStatus.FAILED, RepairStatus.SUCCESS]

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="minute5_bars",
                run=lambda: RepairCheckResult("minute5_bars", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult(
                    "strategy_publish",
                    strategy_status[0],
                    "ready" if strategy_status[0] == RepairStatus.SUCCESS else "missing",
                    blocker=strategy_status[0] == RepairStatus.FAILED,
                ),
            ),
        ]

    def minute_action(trade_date, output_dir):
        calls.append("repair_minute5_bars")
        return RepairActionResult("repair_minute5_bars", RepairStatus.FAILED, "still missing")

    def strategy_action(trade_date, output_dir):
        calls.append("repair_strategy_publish")
        strategy_status.pop(0)
        return RepairActionResult("repair_strategy_publish", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="publish-only",
        check_plan_builder=check_plan_builder,
        action_registry={"minute5_bars": minute_action, "strategy_publish": strategy_action},
    )

    assert calls == ["repair_strategy_publish"]
    assert [stage.name for stage in summary.stages] == ["strategy_eod"]
    assert summary.remaining_blockers == ["minute5_bars"]


def test_run_eod_auto_repair_does_not_recheck_when_no_actions_run(tmp_path):
    calls = {"daily_bars": 0}

    def check_plan_builder(trade_date):
        def run_check():
            calls["daily_bars"] += 1
            status = RepairStatus.SUCCESS if calls["daily_bars"] == 1 else RepairStatus.FAILED
            return RepairCheckResult(
                "daily_bars",
                status,
                "ready" if status == RepairStatus.SUCCESS else "changed",
                blocker=status == RepairStatus.FAILED,
            )

        return [SimpleNamespace(name="daily_bars", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    assert calls["daily_bars"] == 1
    assert summary.actions == []
    assert summary.final_status == RepairStatus.SUCCESS


def test_run_report_contains_stage_blockers_actions_and_next_steps(tmp_path):
    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="reports",
                run=lambda: RepairCheckResult(
                    "reports",
                    RepairStatus.FAILED,
                    "generated reports missing",
                    blocker=False,
                ),
            )
        ]

    run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    report = (tmp_path / "run_report.md").read_text()
    assert "Final status" in report
    assert "Remaining non-blockers" in report
    assert "reports" in report
    assert "Next actions" in report


def test_20260701_incident_flow_repairs_minute_score_watchlist_then_degrades_on_reports(tmp_path):
    state = {
        "minute5_bars": RepairStatus.FAILED,
        "score_topn": RepairStatus.FAILED,
        "watchlist": RepairStatus.FAILED,
        "strategy_publish": RepairStatus.FAILED,
        "reports": RepairStatus.FAILED,
    }
    blockers = {
        "minute5_bars": True,
        "score_topn": True,
        "watchlist": True,
        "strategy_publish": True,
        "reports": False,
    }
    calls = []

    def check_plan_builder(trade_date):
        checks = []
        for name in ["minute5_bars", "score_topn", "watchlist", "strategy_publish", "reports"]:
            def run_check(check_name=name):
                return RepairCheckResult(
                    check_name,
                    state[check_name],
                    "ready" if state[check_name] == RepairStatus.SUCCESS else "missing",
                    blocker=blockers[check_name],
                )

            checks.append(SimpleNamespace(name=name, run=run_check))
        return checks

    def action_for(check_name):
        def action(trade_date, output_dir):
            calls.append(check_name)
            if check_name != "reports":
                state[check_name] = RepairStatus.SUCCESS
            return RepairActionResult(f"repair_{check_name}", RepairStatus.SUCCESS, "ran")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={
            "minute5_bars": action_for("minute5_bars"),
            "score_topn": action_for("score_topn"),
            "watchlist": action_for("watchlist"),
            "strategy_publish": action_for("strategy_publish"),
            "reports": action_for("reports"),
        },
        write_reports=True,
    )

    assert calls == ["minute5_bars", "score_topn", "watchlist", "strategy_publish", "reports"]
    assert summary.final_status == RepairStatus.DEGRADED
    assert summary.remaining_blockers == []
    assert summary.remaining_non_blockers == ["reports"]
