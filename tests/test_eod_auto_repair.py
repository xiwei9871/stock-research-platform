import json
import time
from types import SimpleNamespace

import pandas as pd

import stock_research.reports.daily_research_report_cli as daily_research_report_cli
import stock_research.strategy_eod_publish as strategy_eod_publish
import stock_research.watchlist.workflow as watchlist_workflow
from stock_research.data_run_manifest import build_manifest_entry
import stock_research.eod_auto_repair as eod_auto_repair
import stock_research.eod_auto_repair_actions as eod_auto_repair_actions
from stock_research.eod_auto_repair import build_default_action_registry, run_eod_auto_repair
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairRunSummary, RepairStatus


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


def test_run_eod_auto_repair_loop_dry_run_observes_and_classifies_without_actions(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="score_topn",
                run=lambda: RepairCheckResult("score_topn", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="reports",
                run=lambda: RepairCheckResult("reports", RepairStatus.FAILED, "generated missing", blocker=False),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED,
                    "degraded ready",
                    metrics={"pipeline_status": "DEGRADED_READY"},
                ),
            ),
        ]

    def action_runner(trade_date, output_dir):
        calls.append("repair")
        return RepairActionResult("repair_score_topn", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="loop",
        dry_run=True,
        check_plan_builder=check_plan_builder,
        action_registry={"score_topn": action_runner},
    )

    assert calls == []
    assert summary.final_status == RepairStatus.FAILED
    assert summary.remaining_blockers == ["score_topn"]
    assert summary.initial_classification == {
        "score_topn": "blocker",
        "reports": "degraded_only",
        "ops_health": "healthy",
    }
    assert summary.final_classification["reports"] == "degraded_only"
    assert summary.loop_stop_reason == "dry_run"


def test_run_eod_auto_repair_loop_writes_live_progress_files(tmp_path):
    state = {"minute5_bars": RepairStatus.FAILED}

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="minute5_bars",
                run=lambda: RepairCheckResult(
                    "minute5_bars",
                    state["minute5_bars"],
                    "ready" if state["minute5_bars"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["minute5_bars"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED,
                    "degraded ready",
                    metrics={"pipeline_status": "DEGRADED_READY"},
                ),
            ),
        ]

    def minute_action(trade_date, output_dir):
        state["minute5_bars"] = RepairStatus.SUCCESS
        return RepairActionResult("repair_minute5_bars", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-02",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={"minute5_bars": minute_action},
    )

    latest = json.loads((tmp_path / "repair_progress.json").read_text())
    history = [
        json.loads(line)
        for line in (tmp_path / "repair_progress.jsonl").read_text().splitlines()
    ]

    assert summary.loop_stop_reason == "ready_with_no_blockers"
    assert latest["event"] == "loop_done"
    assert latest["loop_stop_reason"] == "ready_with_no_blockers"
    assert [event["event"] for event in history] == [
        "observe_complete",
        "action_start",
        "action_end",
        "validation_complete",
        "loop_done",
    ]
    assert history[1]["component"] == "minute5_bars"
    assert history[2]["exit_code"] == 0
    assert history[3]["remaining_blockers"] == []


def test_run_eod_auto_repair_loop_resets_stale_progress_history(tmp_path):
    (tmp_path / "repair_progress.jsonl").write_text('{"event": "stale"}\n')
    (tmp_path / "repair_progress.json").write_text('{"event": "stale"}\n')

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.SUCCESS,
                    "ready",
                    metrics={"pipeline_status": "READY"},
                ),
            )
        ]

    run_eod_auto_repair(
        trade_date="2026-07-02",
        output_dir=tmp_path,
        mode="loop",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )

    history = [
        json.loads(line)
        for line in (tmp_path / "repair_progress.jsonl").read_text().splitlines()
    ]

    assert history[0]["event"] == "observe_complete"
    assert all(event["event"] != "stale" for event in history)


def test_run_eod_auto_repair_loop_writes_action_heartbeat_for_slow_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(eod_auto_repair, "ACTION_PROGRESS_HEARTBEAT_SECONDS", 0.01, raising=False)
    state = {"strategy_publish": RepairStatus.FAILED}

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult(
                    "strategy_publish",
                    state["strategy_publish"],
                    "ready" if state["strategy_publish"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["strategy_publish"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED,
                    "degraded ready",
                    metrics={"pipeline_status": "DEGRADED_READY"},
                ),
            ),
        ]

    def slow_action(trade_date, output_dir):
        time.sleep(0.05)
        state["strategy_publish"] = RepairStatus.SUCCESS
        return RepairActionResult("repair_strategy_publish", RepairStatus.SUCCESS, "fixed")

    run_eod_auto_repair(
        trade_date="2026-07-02",
        output_dir=tmp_path,
        mode="loop",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": slow_action},
    )

    history = [
        json.loads(line)
        for line in (tmp_path / "repair_progress.jsonl").read_text().splitlines()
    ]

    heartbeat = next(event for event in history if event["event"] == "action_heartbeat")
    assert heartbeat["component"] == "strategy_publish"
    assert heartbeat["action"] == "strategy_publish"


def test_run_eod_auto_repair_loop_repairs_blockers_in_cycles_and_does_not_chase_reports(tmp_path):
    state = {
        "factor_daily": RepairStatus.FAILED,
        "score_topn": RepairStatus.FAILED,
        "watchlist": RepairStatus.FAILED,
        "reports": RepairStatus.FAILED,
    }
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="factor_daily",
                run=lambda: RepairCheckResult(
                    "factor_daily",
                    state["factor_daily"],
                    "ready" if state["factor_daily"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["factor_daily"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="score_topn",
                run=lambda: RepairCheckResult(
                    "score_topn",
                    state["score_topn"],
                    "ready" if state["score_topn"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["score_topn"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="watchlist",
                run=lambda: RepairCheckResult(
                    "watchlist",
                    state["watchlist"],
                    "ready" if state["watchlist"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["watchlist"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="reports",
                run=lambda: RepairCheckResult("reports", state["reports"], "generated missing", blocker=False),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED,
                    "degraded ready",
                    metrics={"pipeline_status": "DEGRADED_READY"},
                ),
            ),
        ]

    def action_for(check_name):
        def action(trade_date, output_dir):
            calls.append(check_name)
            state[check_name] = RepairStatus.SUCCESS
            return RepairActionResult(f"repair_{check_name}", RepairStatus.SUCCESS, "fixed")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "factor_daily": action_for("factor_daily"),
            "score_topn": action_for("score_topn"),
            "watchlist": action_for("watchlist"),
            "reports": action_for("reports"),
        },
        write_reports=True,
    )

    assert calls == ["factor_daily", "score_topn", "watchlist"]
    assert summary.final_status == RepairStatus.DEGRADED
    assert summary.remaining_blockers == []
    assert summary.remaining_non_blockers == ["reports"]
    assert summary.loop_stop_reason == "ready_with_no_blockers"
    assert summary.loop_cycles[0].cycle_number == 1
    assert "System is usable" in (tmp_path / "run_report.md").read_text()


def test_run_eod_auto_repair_loop_runs_factor_dependents_before_stopping(tmp_path):
    state = {
        "factor_daily": RepairStatus.FAILED,
        "score_topn": RepairStatus.SUCCESS,
        "watchlist": RepairStatus.SUCCESS,
        "market_monitor": RepairStatus.SUCCESS,
        "strategy_publish": RepairStatus.SUCCESS,
        "reports": RepairStatus.FAILED,
    }
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name=name,
                run=lambda check_name=name: RepairCheckResult(
                    check_name,
                    state[check_name],
                    "ready" if state[check_name] == RepairStatus.SUCCESS else "missing",
                    blocker=check_name == "factor_daily" and state[check_name] != RepairStatus.SUCCESS,
                ),
            )
            for name in [
                "factor_daily",
                "score_topn",
                "watchlist",
                "market_monitor",
                "strategy_publish",
                "reports",
            ]
        ] + [
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED,
                    "degraded ready",
                    metrics={"pipeline_status": "DEGRADED_READY"},
                ),
            )
        ]

    def action_for(check_name):
        def action(trade_date, output_dir):
            calls.append(check_name)
            state[check_name] = RepairStatus.SUCCESS
            return RepairActionResult(f"repair_{check_name}", RepairStatus.SUCCESS, "fixed")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "factor_daily": action_for("factor_daily"),
            "score_topn": action_for("score_topn"),
            "watchlist": action_for("watchlist"),
            "market_monitor": action_for("market_monitor"),
            "strategy_publish": action_for("strategy_publish"),
            "reports": action_for("reports"),
        },
    )

    assert calls == ["factor_daily", "score_topn", "watchlist", "market_monitor", "strategy_publish"]
    assert summary.remaining_blockers == []
    assert summary.remaining_non_blockers == ["reports"]
    assert summary.actions[0].validation_result["component"] == "factor_daily"
    assert summary.loop_stop_reason == "ready_with_no_blockers"


def test_run_eod_auto_repair_loop_finalizes_ops_health_after_market_monitor_repair(tmp_path):
    state = {
        "market_monitor": RepairStatus.FAILED,
        "ops_health": RepairStatus.FAILED,
    }
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="market_monitor",
                run=lambda: RepairCheckResult(
                    "market_monitor",
                    state["market_monitor"],
                    "ready" if state["market_monitor"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["market_monitor"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.DEGRADED if state["ops_health"] == RepairStatus.SUCCESS else RepairStatus.FAILED,
                    "degraded ready" if state["ops_health"] == RepairStatus.SUCCESS else "not ready",
                    metrics={
                        "pipeline_status": "DEGRADED_READY"
                        if state["ops_health"] == RepairStatus.SUCCESS
                        else "NOT_READY"
                    },
                    blocker=state["ops_health"] != RepairStatus.SUCCESS,
                ),
            ),
        ]

    def market_monitor_action(trade_date, output_dir):
        calls.append("market_monitor")
        state["market_monitor"] = RepairStatus.SUCCESS
        return RepairActionResult("repair_market_monitor", RepairStatus.SUCCESS, "fixed")

    def ops_health_action(trade_date, output_dir):
        calls.append("ops_health")
        state["ops_health"] = RepairStatus.SUCCESS
        return RepairActionResult("finalize_ops_health", RepairStatus.SUCCESS, "finalized")

    summary = run_eod_auto_repair(
        trade_date="2026-07-02",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "market_monitor": market_monitor_action,
            "ops_health": ops_health_action,
        },
    )

    assert calls == ["market_monitor", "ops_health"]
    assert summary.remaining_blockers == []
    assert summary.loop_stop_reason == "ready_with_no_blockers"
    assert summary.actions[-1].validation_result["component"] == "ops_health"


def test_run_eod_auto_repair_loop_stops_after_repeated_action_failures(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.FAILED,
                    "not ready",
                    metrics={"pipeline_status": "FAILED"},
                    blocker=True,
                ),
            ),
        ]

    def action_runner(trade_date, output_dir):
        calls.append("repair_strategy_publish")
        return RepairActionResult("repair_strategy_publish", RepairStatus.FAILED, "source unavailable")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": action_runner},
    )

    assert calls == ["repair_strategy_publish", "repair_strategy_publish"]
    assert summary.final_status == RepairStatus.FAILED
    assert summary.loop_stop_reason == "failed_action_repeat_limit:strategy_publish"


def test_run_eod_auto_repair_loop_bounds_individual_action_runtime(tmp_path):
    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.FAILED,
                    "not ready",
                    metrics={"pipeline_status": "BLOCKED"},
                    blocker=True,
                ),
            ),
        ]

    def slow_action(trade_date, output_dir):
        time.sleep(10)
        return RepairActionResult("repair_strategy_publish", RepairStatus.SUCCESS, "unexpected")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        action_timeout_seconds=1,
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": slow_action},
    )

    assert summary.loop_stop_reason == "failed_action_repeat_limit:strategy_publish"
    assert len(summary.actions) == 2
    assert [action.exit_code for action in summary.actions] == [124, 124]
    assert "TimeoutError" in summary.actions[0].message


def test_cli_defaults_output_dir_for_loop_mode(monkeypatch, tmp_path):
    captured = {}

    def fake_registry(*, output_root):
        return {}

    def fake_run_eod_auto_repair(**kwargs):
        captured.update(kwargs)
        return eod_auto_repair.RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=RepairStatus.DEGRADED,
        )

    monkeypatch.setattr(eod_auto_repair, "build_default_action_registry", fake_registry)
    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", fake_run_eod_auto_repair)

    rc = eod_auto_repair._main(
        [
            "--trade-date",
            "2026-07-01",
            "--mode",
            "loop",
            "--dry-run",
            "--report-json",
            str(tmp_path / "eod-loop-test.json"),
        ]
    )

    assert rc == 0
    assert str(captured["output_dir"]).endswith("outputs/research/eod_auto_repair/2026-07-01")
    assert captured["action_timeout_seconds"] == 43200


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


def test_run_eod_auto_repair_writes_report_with_path_metrics(tmp_path):
    def check_plan_builder(trade_date):
        results = [
            RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready"),
        ]

        def run_check():
            return results.pop(0)

        return [SimpleNamespace(name="strategy_publish", run=run_check)]

    def action_runner(trade_date, output_dir):
        return RepairActionResult(
            "publish_strategy_eod",
            RepairStatus.SUCCESS,
            "published",
            metrics={
                "report_paths": {
                    "topn": {
                        "markdown_path": tmp_path / "reports" / "topn.md",
                    },
                },
            },
        )

    run_eod_auto_repair(
        trade_date="2026-07-02",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": action_runner},
        write_reports=True,
    )

    payload = json.loads((tmp_path / "run_summary.json").read_text())
    markdown_path = payload["actions"][0]["metrics"]["report_paths"]["topn"]["markdown_path"]
    assert markdown_path == str(tmp_path / "reports" / "topn.md")
    assert str(tmp_path / "reports" / "topn.md") in (tmp_path / "run_report.md").read_text()


def test_eod_auto_repair_cli_prints_summary_with_path_metrics(monkeypatch, tmp_path, capsys):
    report_json = tmp_path / "summary.json"
    path_metric = tmp_path / "reports" / "topn.md"

    def fake_registry(output_root):
        return {}

    def fake_run_eod_auto_repair(**kwargs):
        return RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=RepairStatus.SUCCESS,
            actions=[
                RepairActionResult(
                    "publish_strategy_eod",
                    RepairStatus.SUCCESS,
                    metrics={"report_paths": {"topn": {"markdown_path": path_metric}}},
                )
            ],
        )

    monkeypatch.setattr(eod_auto_repair, "build_default_action_registry", fake_registry)
    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", fake_run_eod_auto_repair)

    rc = eod_auto_repair._main(
        [
            "--trade-date",
            "2026-07-02",
            "--output-dir",
            str(tmp_path / "out"),
            "--report-json",
            str(report_json),
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["actions"][0]["metrics"]["report_paths"]["topn"]["markdown_path"] == str(
        path_metric
    )
    assert json.loads(report_json.read_text())["actions"][0]["metrics"]["report_paths"]["topn"]["markdown_path"] == str(
        path_metric
    )


def test_default_action_registry_contains_repairable_checks():
    registry = build_default_action_registry(output_root="outputs")

    assert "minute5_bars" in registry
    assert "technical_features" in registry
    assert "lhb_features" in registry
    assert "score_topn" in registry
    assert "watchlist" in registry
    assert "market_monitor" in registry
    assert "strategy_publish" in registry
    assert "ops_health" in registry
    assert "reports" in registry
    assert "review_evidence_snapshots" in registry


def test_default_minute5_action_uses_direct_raw_repair(monkeypatch, tmp_path):
    captured = {}

    def fake_repair_minute5_raw_bars(trade_date, **kwargs):
        captured["trade_date"] = trade_date
        captured["kwargs"] = kwargs
        return RepairActionResult(
            "repair_minute5_raw_bars",
            RepairStatus.SUCCESS,
            metrics={"attempted": 1, "rows": 48, "qfq_rows": 48},
        )

    monkeypatch.setattr(eod_auto_repair_actions, "repair_minute5_raw_bars", fake_repair_minute5_raw_bars)

    registry = build_default_action_registry(output_root="outputs")
    result = registry["minute5_bars"]("2026-07-06", tmp_path)

    assert result.name == "repair_minute5_raw_bars"
    assert captured["trade_date"] == "2026-07-06"
    assert captured["kwargs"]["service"] != ""
    assert callable(captured["kwargs"]["missing_symbols_loader"])
    assert callable(captured["kwargs"]["raw_fetcher"])
    assert callable(captured["kwargs"]["upserter"])
    assert callable(captured["kwargs"]["qfq_deriver"])
    assert callable(captured["kwargs"]["quality_refresher"])
    assert captured["kwargs"]["symbol_sleep_seconds"] == 0.75


def test_default_market_monitor_action_runs_source_stage_before_dashboard(monkeypatch, tmp_path):
    import stock_research.daily_close_pipeline as daily_close_pipeline
    import stock_research.dashboard.market_monitor as market_monitor

    calls = []

    def fake_run_market_monitor_stage(trade_date, *, config):
        calls.append(("stage", trade_date.isoformat(), config.service))
        return {"stage": "market_monitor", "status": "success", "rows": 8}

    def fake_build_market_monitor_eod(**kwargs):
        calls.append(("dashboard", kwargs["trade_date"]))
        return {"trade_date": kwargs["trade_date"], "market_emotion": {"summary": {"status": "ok"}}}

    monkeypatch.setattr(daily_close_pipeline, "run_market_monitor_stage", fake_run_market_monitor_stage)
    monkeypatch.setattr(market_monitor, "build_market_monitor_eod", fake_build_market_monitor_eod)

    registry = build_default_action_registry(output_root="outputs")
    result = registry["market_monitor"]("2026-07-02", tmp_path)

    assert result.status == RepairStatus.SUCCESS
    assert calls == [("stage", "2026-07-02", daily_close_pipeline.SETTINGS.research_service), ("dashboard", "2026-07-02")]
    assert result.metrics["stage"]["status"] == "success"
    assert result.metrics["dashboard"]["trade_date"] == "2026-07-02"


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
