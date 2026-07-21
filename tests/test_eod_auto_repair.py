import json
import hashlib
import os
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import stock_research.reports.daily_research_report_cli as daily_research_report_cli
import stock_research.strategy_eod_publish as strategy_eod_publish
import stock_research.watchlist.workflow as watchlist_workflow
from stock_research.data_run_manifest import build_manifest_entry
import stock_research.eod_auto_repair as eod_auto_repair
import stock_research.eod_auto_repair_actions as eod_auto_repair_actions
import stock_research.eod_auto_repair_checks as eod_auto_repair_checks
import stock_research.eod_auto_repair_report as eod_auto_repair_report
import stock_research.daily_close_pipeline as daily_close_pipeline
from stock_research.eod_auto_repair import build_default_action_registry, run_eod_auto_repair
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairRunSummary, RepairStatus
from stock_research.eod_browser_acceptance import (
    REPORT_SCHEMA_VERSION,
    parse_browser_acceptance_report,
    run_browser_acceptance,
    select_latest_strategy_candidate_publications,
    write_browser_acceptance_manifest,
)


BROWSER_STRATEGY_IDS = ("lhb_shortline", "mid_trend", "tech_bottleneck")


def _browser_candidate(strategy_id, *, trade_date="2026-07-20", hour=1, run_id="strategy-run-1"):
    return {
        "strategyId": strategy_id,
        "tradeDate": trade_date,
        "totalReturnPct": 52.4 + hour,
        "contractId": f"{strategy_id}:balanced:v1",
        "publishId": f"{strategy_id}-publish-{trade_date}",
        "publishStartedAt": f"{trade_date}T{hour:02d}:00:00+00:00",
        "artifactVersion": "strategy-publication/v1",
        "runId": run_id,
    }


def _strategy_manifest_rows(*, trade_date="2026-07-20", run_id="strategy-run-1"):
    rows = []
    for index, strategy_id in enumerate(BROWSER_STRATEGY_IDS):
        candidate = _browser_candidate(
            strategy_id,
            trade_date=trade_date,
            hour=index + 1,
            run_id=run_id,
        )
        rows.append(
            {
                "module": f"strategy_{strategy_id}",
                "source": "strategy_daily_eod",
                "status": "success",
                "trade_date": trade_date,
                "latest_trade_date": trade_date,
                "run_id": run_id,
                "started_at": candidate["publishStartedAt"],
                "ended_at": candidate["publishStartedAt"],
                "metadata": {
                    "publish_id": candidate["publishId"],
                    "artifact_version": candidate["artifactVersion"],
                    "publication_identity": {
                        "strategy_id": strategy_id,
                        "contract_id": candidate["contractId"],
                    },
                    "summary": {
                        "total_return_pct": candidate["totalReturnPct"],
                        "artifact_version": candidate["artifactVersion"],
                        "publication_identity": {
                            "strategy_id": strategy_id,
                            "contract_id": candidate["contractId"],
                        },
                    },
                },
            }
        )
    return rows


def _write_browser_report(
    path,
    *,
    candidates,
    trade_date="2026-07-20",
    run_id="strategy-run-1",
    status="success",
    failures=(),
    failed_gate=None,
):
    snapshot = {
        "schemaVersion": "playwright-eod-candidate-snapshot/v1",
        "tradeDate": trade_date,
        "publications": [
            {key: value for key, value in candidate.items() if key != "runId"}
            for candidate in candidates
        ],
    }
    snapshot_digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    tests = [
        {
            "testId": f"test-{gate_id}",
            "title": f"@eod @eod-gate-{gate_id} gate {gate_id}",
            "projectName": "eod-chromium",
            "retry": 0,
            "status": "failed" if gate_id == failed_gate else "passed",
            "durationMs": 25,
            "failures": list(failures) if gate_id == failed_gate else [],
            "attachments": [],
            "severity": "blocker-runtime" if gate_id == failed_gate else "blocker-consistency",
            "attemptHistory": [
                {
                    "retry": 0,
                    "status": "failed" if gate_id == failed_gate else "passed",
                    "durationMs": 25,
                    "failures": list(failures) if gate_id == failed_gate else [],
                    "attachments": [],
                }
            ],
        }
        for gate_id in (
            "candidate-consistency",
            "publication-consistency",
            "runtime-deep-links",
        )
    ]
    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "runId": run_id,
        "tradeDate": trade_date,
        "revision": "abc123",
        "startedAt": f"{trade_date}T08:00:00+00:00",
        "endedAt": f"{trade_date}T08:00:02+00:00",
        "durationSeconds": 2.0,
        "contractOnly": False,
        "status": status,
        "tests": tests,
        "failures": list(failures),
        "attachments": [],
        "candidateSnapshot": snapshot,
        "candidateSnapshotSha256": snapshot_digest,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _verified_browser_result(tmp_path, *, candidates, trade_date="2026-07-20", run_id="strategy-run-1"):
    report_path = _write_browser_report(
        tmp_path / "browser-run" / "eod-browser-acceptance.json",
        candidates=candidates,
        trade_date=trade_date,
        run_id=run_id,
    )
    return parse_browser_acceptance_report(
        report_path,
        expected_run_id=run_id,
        expected_trade_date=trade_date,
        expected_revision="abc123",
        expected_candidate_publications=candidates,
        exit_code=0,
    )


def _previous_browser_publications(candidates, *, trade_date="2026-07-20"):
    return {
        "schemaVersion": "playwright-eod-previous-publications/v1",
        "publications": [
            {
                **{key: value for key, value in candidate.items() if key != "runId"},
                "tradeDate": "2026-07-19",
                "publishId": candidate["publishId"].replace(trade_date, "2026-07-19"),
                "publishStartedAt": candidate["publishStartedAt"].replace(
                    trade_date,
                    "2026-07-19",
                ),
            }
            for candidate in candidates
        ],
    }


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


def test_run_eod_auto_repair_generates_unique_and_accepts_injected_run_id(tmp_path):
    def check_plan_builder(_trade_date):
        return [
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
            )
        ]

    first = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path / "first",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )
    second = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path / "second",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
    )
    injected = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path / "injected",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        run_id="eod-fixed-test-run",
    )

    assert first.run_id
    assert second.run_id
    assert first.run_id != second.run_id
    assert injected.run_id == "eod-fixed-test-run"


@pytest.mark.parametrize("mode", ["check", "repair", "loop"])
def test_run_eod_auto_repair_uses_injected_run_id_in_all_top_level_modes(tmp_path, mode):
    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path / mode,
        mode=mode,
        check_plan_builder=lambda _trade_date: [
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
            )
        ],
        action_registry={},
        run_id=f"eod-fixed-{mode}",
    )

    assert summary.run_id == f"eod-fixed-{mode}"


def test_loop_default_disabled_filters_browser_before_check_run(tmp_path):
    browser_check_calls = []
    browser_action_calls = []

    def check_plan_builder(_trade_date):
        return [
            SimpleNamespace(
                name="dashboard_browser_acceptance",
                run=lambda: browser_check_calls.append("run")
                or RepairCheckResult(
                    "dashboard_browser_acceptance",
                    RepairStatus.FAILED,
                    "must stay disabled",
                    blocker=True,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
            ),
        ]

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path,
        mode="loop",
        check_plan_builder=check_plan_builder,
        action_registry={
            "dashboard_browser_acceptance": lambda *_args: browser_action_calls.append("run")
            or RepairActionResult("dashboard_browser_acceptance", RepairStatus.SUCCESS)
        },
    )

    assert browser_check_calls == []
    assert browser_action_calls == []
    assert all(check.name != "dashboard_browser_acceptance" for check in summary.checks_after)


def test_loop_enabled_runs_browser_check_and_action(tmp_path):
    state = {"browser": RepairStatus.FAILED}
    browser_check_calls = []
    browser_action_calls = []

    def check_plan_builder(_trade_date):
        return [
            SimpleNamespace(
                name="dashboard_browser_acceptance",
                run=lambda: browser_check_calls.append("run")
                or RepairCheckResult(
                    "dashboard_browser_acceptance",
                    state["browser"],
                    "ready" if state["browser"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["browser"] != RepairStatus.SUCCESS,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
            ),
        ]

    def browser_action(*_args):
        browser_action_calls.append("run")
        state["browser"] = RepairStatus.SUCCESS
        return RepairActionResult("dashboard_browser_acceptance", RepairStatus.SUCCESS)

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path,
        mode="loop",
        check_plan_builder=check_plan_builder,
        action_registry={"dashboard_browser_acceptance": browser_action},
        browser_acceptance_enabled=True,
    )

    assert len(browser_check_calls) >= 2
    assert browser_action_calls == ["run"]
    assert any(action.name == "dashboard_browser_acceptance" for action in summary.actions)


@pytest.mark.parametrize("mode", ["check", "repair", "publish-only"])
def test_non_loop_modes_exclude_browser_acceptance_check_and_action(mode, tmp_path):
    browser_check_calls = []
    browser_action_calls = []

    def check_plan_builder(trade_date):
        def browser_check():
            browser_check_calls.append(trade_date)
            return RepairCheckResult(
                "dashboard_browser_acceptance",
                RepairStatus.FAILED,
                "missing",
                blocker=True,
            )

        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready"),
            ),
            SimpleNamespace(name="dashboard_browser_acceptance", run=browser_check),
            SimpleNamespace(
                name="dashboard_surface_freshness",
                run=lambda: RepairCheckResult(
                    "dashboard_surface_freshness", RepairStatus.SUCCESS, "ready"
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.SUCCESS,
                    "ready",
                    metrics={"pipeline_status": "READY"},
                ),
            ),
        ]

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path / mode,
        mode=mode,
        check_plan_builder=check_plan_builder,
        action_registry={
            "dashboard_browser_acceptance": lambda trade_date, output_dir: browser_action_calls.append(
                trade_date
            )
            or RepairActionResult(
                "dashboard_browser_acceptance", RepairStatus.SUCCESS, "unexpected"
            )
        },
    )

    assert browser_check_calls == []
    assert browser_action_calls == []
    assert summary.final_status == RepairStatus.SUCCESS
    assert all(check.name != "dashboard_browser_acceptance" for check in summary.checks_before)
    assert all(check.name != "dashboard_browser_acceptance" for check in summary.checks_after)
    assert all(action.name != "dashboard_browser_acceptance" for action in summary.actions)
    assert all(
        check.name != "dashboard_browser_acceptance"
        for stage in summary.stages
        for check in stage.checks_before + stage.checks_after
    )


def test_check_minute5_bars_requires_raw_and_qfq_quality():
    captured = {}

    def fake_fetcher(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "raw_expected_count": 5190,
                "raw_actual_count": 5190,
                "raw_missing_count": 0,
                "raw_abnormal_count": 0,
                "qfq_expected_count": 5190,
                "qfq_actual_count": 5000,
                "qfq_missing_count": 190,
                "qfq_abnormal_count": 0,
            }
        ]

    result = eod_auto_repair_checks.check_minute5_bars(
        "2026-07-10",
        fetcher=fake_fetcher,
    )

    assert "minute5_qfq_bar" in captured["sql"]
    assert captured["params"] == ["2026-07-10"]
    assert result.status == RepairStatus.FAILED
    assert result.metrics["raw_missing_count"] == 0
    assert result.metrics["qfq_missing_count"] == 190


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
    assert (tmp_path / "run_report.html").exists()


def test_run_eod_auto_repair_surfaces_html_report_failure(monkeypatch, tmp_path):
    def fail_html(_summary, _output_dir):
        raise OSError("html unavailable")

    monkeypatch.setattr(eod_auto_repair_report, "render_html_report", fail_html)

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=lambda _trade_date: [
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
            )
        ],
        action_registry={},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert any("run_report_html_failed" in issue for issue in summary.infrastructure_issues)
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()
    assert not (tmp_path / "run_report.html").exists()


def test_cli_returns_failure_when_report_generation_fails(monkeypatch, tmp_path):
    original_run = run_eod_auto_repair

    def fail_html(_summary, _output_dir):
        raise OSError("html unavailable")

    def run_with_controlled_checks(**kwargs):
        return original_run(
            **kwargs,
            check_plan_builder=lambda _trade_date: [
                SimpleNamespace(
                    name="ops_health",
                    run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
                )
            ],
        )

    monkeypatch.setattr(eod_auto_repair_report, "render_html_report", fail_html)
    monkeypatch.setattr(eod_auto_repair, "build_default_action_registry", lambda **_kwargs: {})
    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", run_with_controlled_checks)

    rc = eod_auto_repair._main(
        [
            "--trade-date",
            "2026-07-01",
            "--output-dir",
            str(tmp_path),
            "--mode",
            "check",
        ]
    )

    assert rc == 2


def test_cli_returns_failure_when_retention_cleanup_fails(monkeypatch, tmp_path):
    original_run = run_eod_auto_repair

    def fail_retention(*_args, **_kwargs):
        raise PermissionError("retention denied")

    def run_with_controlled_checks(**kwargs):
        return original_run(
            **kwargs,
            check_plan_builder=lambda _trade_date: [
                SimpleNamespace(
                    name="ops_health",
                    run=lambda: RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready"),
                )
            ],
        )

    monkeypatch.setattr(eod_auto_repair_report, "prune_report_retention", fail_retention)
    monkeypatch.setattr(eod_auto_repair, "build_default_action_registry", lambda **_kwargs: {})
    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", run_with_controlled_checks)

    rc = eod_auto_repair._main(
        [
            "--trade-date",
            "2026-07-01",
            "--output-dir",
            str(tmp_path),
            "--mode",
            "check",
        ]
    )

    assert rc == 2
    assert json.loads((tmp_path / "run_summary.json").read_text())["final_status"] == "failed"


def test_cli_report_copies_are_private_and_reject_symlinks(monkeypatch, tmp_path):
    def fake_registry(**_kwargs):
        return {}

    def fake_run(**kwargs):
        output = kwargs["output_dir"]
        os.makedirs(output, exist_ok=True)
        with open(os.path.join(output, "run_report.md"), "w", encoding="utf-8") as handle:
            handle.write("report\n")
        return RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=RepairStatus.SUCCESS,
            run_id="eod-copy-test",
        )

    monkeypatch.setattr(eod_auto_repair, "build_default_action_registry", fake_registry)
    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", fake_run)
    report_json = tmp_path / "copies" / "summary.json"
    report_md = tmp_path / "copies" / "report.md"

    rc = eod_auto_repair._main(
        [
            "--trade-date",
            "2026-07-01",
            "--output-dir",
            str(tmp_path / "out"),
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
        ]
    )

    assert rc == 0
    assert report_json.stat().st_mode & 0o777 == 0o600
    assert report_md.stat().st_mode & 0o777 == 0o600
    symlink = tmp_path / "summary-link.json"
    symlink.symlink_to(report_json)
    with pytest.raises(ValueError, match="symlink"):
        eod_auto_repair._main(
            [
                "--trade-date",
                "2026-07-01",
                "--output-dir",
                str(tmp_path / "out-2"),
                "--report-json",
                str(symlink),
            ]
        )


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


def test_run_eod_auto_repair_loop_skips_browser_and_downstream_when_upstream_blocker_remains(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name=name,
                run=lambda check_name=name: RepairCheckResult(
                    check_name,
                    RepairStatus.FAILED,
                    "blocked",
                    metrics={"pipeline_status": "BLOCKED"} if check_name == "ops_health" else {},
                    blocker=True,
                ),
            )
            for name in (
                "strategy_publish",
                "dashboard_browser_acceptance",
                "dashboard_surface_freshness",
                "ops_health",
            )
        ]

    def action_for(name):
        def action(trade_date, output_dir):
            calls.append(name)
            return RepairActionResult(name, RepairStatus.SUCCESS, "unexpected")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "dashboard_browser_acceptance": action_for("dashboard_browser_acceptance"),
            "dashboard_surface_freshness": action_for("dashboard_surface_freshness"),
            "ops_health": action_for("ops_health"),
        },
    )

    assert calls == []
    assert summary.final_status == RepairStatus.FAILED
    assert "strategy_publish" in summary.remaining_blockers


def test_run_eod_auto_repair_loop_attempts_failed_browser_once_and_blocks_downstream(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready"),
            ),
            SimpleNamespace(
                name="dashboard_browser_acceptance",
                run=lambda: RepairCheckResult(
                    "dashboard_browser_acceptance",
                    RepairStatus.FAILED,
                    "consistency failed",
                    blocker=True,
                ),
            ),
            SimpleNamespace(
                name="dashboard_surface_freshness",
                run=lambda: RepairCheckResult(
                    "dashboard_surface_freshness",
                    RepairStatus.FAILED,
                    "blocked",
                    blocker=True,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    RepairStatus.FAILED,
                    "blocked",
                    metrics={"pipeline_status": "BLOCKED"},
                    blocker=True,
                ),
            ),
        ]

    def browser_action(trade_date, output_dir):
        calls.append("dashboard_browser_acceptance")
        return RepairActionResult(
            "dashboard_browser_acceptance",
            RepairStatus.FAILED,
            "api_ui_mismatch",
            validation_result={"evidence": {"failure_classes": ["api_ui_mismatch"]}},
        )

    def downstream_action(name):
        return lambda trade_date, output_dir: calls.append(name) or RepairActionResult(
            name,
            RepairStatus.SUCCESS,
            "unexpected",
        )

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "dashboard_browser_acceptance": browser_action,
            "dashboard_surface_freshness": downstream_action("dashboard_surface_freshness"),
            "ops_health": downstream_action("ops_health"),
        },
        browser_acceptance_enabled=True,
    )

    assert calls == ["dashboard_browser_acceptance"]
    assert summary.final_status == RepairStatus.FAILED
    assert summary.loop_stop_reason == "failed_action_repeat_limit:dashboard_browser_acceptance"
    assert summary.actions[0].validation_result["evidence"]["failure_classes"] == [
        "api_ui_mismatch"
    ]


def test_run_eod_auto_repair_loop_keeps_degraded_browser_publishable_and_finalizes_in_order(tmp_path):
    state = {
        "dashboard_browser_acceptance": RepairStatus.FAILED,
        "dashboard_surface_freshness": RepairStatus.FAILED,
        "ops_health": RepairStatus.FAILED,
    }
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="strategy_publish",
                run=lambda: RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready"),
            ),
            SimpleNamespace(
                name="dashboard_browser_acceptance",
                run=lambda: RepairCheckResult(
                    "dashboard_browser_acceptance",
                    state["dashboard_browser_acceptance"],
                    "publishable warnings"
                    if state["dashboard_browser_acceptance"] == RepairStatus.DEGRADED
                    else "missing",
                    metrics={"warnings": ["console warning"]}
                    if state["dashboard_browser_acceptance"] == RepairStatus.DEGRADED
                    else {},
                    blocker=state["dashboard_browser_acceptance"] == RepairStatus.FAILED,
                ),
            ),
            SimpleNamespace(
                name="dashboard_surface_freshness",
                run=lambda: RepairCheckResult(
                    "dashboard_surface_freshness",
                    state["dashboard_surface_freshness"],
                    "ready" if state["dashboard_surface_freshness"] == RepairStatus.SUCCESS else "missing",
                    blocker=state["dashboard_surface_freshness"] == RepairStatus.FAILED,
                ),
            ),
            SimpleNamespace(
                name="ops_health",
                run=lambda: RepairCheckResult(
                    "ops_health",
                    state["ops_health"],
                    "ready" if state["ops_health"] == RepairStatus.SUCCESS else "missing",
                    metrics={
                        "pipeline_status": "READY"
                        if state["ops_health"] == RepairStatus.SUCCESS
                        else "BLOCKED"
                    },
                    blocker=state["ops_health"] == RepairStatus.FAILED,
                ),
            ),
        ]

    def browser_action(trade_date, output_dir):
        calls.append("dashboard_browser_acceptance")
        state["dashboard_browser_acceptance"] = RepairStatus.DEGRADED
        return RepairActionResult(
            "dashboard_browser_acceptance",
            RepairStatus.DEGRADED,
            "publishable warnings",
            validation_result={"evidence": {"warnings": ["console warning"]}},
        )

    def success_action(name):
        def action(trade_date, output_dir):
            calls.append(name)
            state[name] = RepairStatus.SUCCESS
            return RepairActionResult(name, RepairStatus.SUCCESS, "ready")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-20",
        output_dir=tmp_path,
        mode="loop",
        max_cycles=3,
        check_plan_builder=check_plan_builder,
        action_registry={
            "dashboard_browser_acceptance": browser_action,
            "dashboard_surface_freshness": success_action("dashboard_surface_freshness"),
            "ops_health": success_action("ops_health"),
        },
        browser_acceptance_enabled=True,
    )

    assert calls == [
        "dashboard_browser_acceptance",
        "dashboard_surface_freshness",
        "ops_health",
    ]
    assert summary.final_status == RepairStatus.DEGRADED
    assert summary.remaining_blockers == []
    assert summary.checks_after[1].metrics["warnings"] == ["console warning"]
    assert summary.actions[0].validation_result["evidence"]["warnings"] == [
        "console warning"
    ]


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

    def fake_registry(*, output_root, browser_acceptance_enabled):
        captured["browser_acceptance_enabled"] = browser_acceptance_enabled
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
    assert captured["browser_acceptance_enabled"] is False


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

    def fake_registry(*, output_root, browser_acceptance_enabled):
        assert browser_acceptance_enabled is False
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
    assert type(registry) is dict
    assert "dashboard_browser_acceptance" not in registry
    assert "ops_health" in registry
    assert "reports" in registry
    assert "review_evidence_snapshots" in registry

    enabled = build_default_action_registry(
        output_root="outputs",
        browser_acceptance_enabled=True,
    )
    assert type(enabled) is dict
    assert "dashboard_browser_acceptance" in enabled


def test_dashboard_cache_clearer_posts_safe_auth_json_and_write_token():
    requests = []

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return Response()

    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url="http://127.0.0.1:8765/api/dashboard/cache/clear",
        login_url="http://127.0.0.1:8765/api/auth/login",
        username='admin"name',
        password="line\nbreak",
        write_token="write-token",
        timeout_seconds=3.5,
        opener=Opener(),
    )

    clearer()

    assert [request.full_url for request, _timeout in requests] == [
        "http://127.0.0.1:8765/api/auth/login",
        "http://127.0.0.1:8765/api/dashboard/cache/clear",
    ]
    assert all(timeout == 3.5 for _request, timeout in requests)
    assert json.loads(requests[0][0].data) == {
        "username": 'admin"name',
        "password": "line\nbreak",
    }
    assert requests[1][0].get_header("X-dashboard-write-token") == "write-token"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///tmp/cache",
        "ftp://127.0.0.1/api/dashboard/cache/clear",
        "http://8.8.8.8/api/dashboard/cache/clear",
        "http://localhost/api/dashboard/cache/clear",
        "http://dashboard.test/api/dashboard/cache/clear",
        "http://127.0.0.1:0/api/dashboard/cache/clear",
        "http://127.0.0.1:65536/api/dashboard/cache/clear",
        "http://user:pass@127.0.0.1/api/dashboard/cache/clear",
        "http://127.0.0.1/wrong",
        "http://127.0.0.1/api/dashboard/cache/clear?force=1",
        "http://127.0.0.1/api/dashboard/cache/clear?",
        "http://127.0.0.1/api/dashboard/cache/clear#fragment",
        "http://127.0.0.1/api/dashboard/cache/clear#",
    ],
)
def test_dashboard_cache_clearer_rejects_missing_or_unsafe_url(url):
    clearer = eod_auto_repair.build_dashboard_cache_clearer(cache_url=url)

    with pytest.raises(RuntimeError, match="cache clear URL"):
        clearer()


def test_dashboard_cache_clearer_rejects_non_2xx_and_redacts_exception():
    class Response:
        status = 503

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, _request, timeout):
            assert timeout == 5.0
            return Response()

    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url="http://127.0.0.1:8765/api/dashboard/cache/clear",
        write_token="do-not-leak",
        opener=Opener(),
    )

    with pytest.raises(RuntimeError, match="http_status_503") as exc_info:
        clearer()

    assert "do-not-leak" not in str(exc_info.value)


def test_dashboard_cache_clearer_redacts_network_exception_details():
    class Opener:
        def open(self, _request, timeout):
            assert timeout == 5.0
            raise OSError("network failed with password=do-not-leak")

    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url="https://127.0.0.1:8765/api/dashboard/cache/clear",
        opener=Opener(),
    )

    with pytest.raises(RuntimeError, match="request failed:OSError") as exc_info:
        clearer()

    assert "do-not-leak" not in str(exc_info.value)


@pytest.mark.parametrize(
    "login_url",
    [
        "https://127.0.0.1:8765/api/auth/login",
        "http://127.0.0.2:8765/api/auth/login",
        "http://127.0.0.1:8766/api/auth/login",
        "http://localhost:8765/api/auth/login",
        "http://user:pass@127.0.0.1:8765/api/auth/login",
        "http://127.0.0.1:8765/wrong",
        "http://127.0.0.1:8765/api/auth/login?next=/",
        "http://127.0.0.1:8765/api/auth/login?",
        "http://127.0.0.1:8765/api/auth/login#fragment",
        "http://127.0.0.1:8765/api/auth/login#",
    ],
)
def test_dashboard_cache_clearer_rejects_login_outside_cache_origin(login_url):
    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url="http://127.0.0.1:8765/api/dashboard/cache/clear",
        login_url=login_url,
        username="admin",
        password="password",
        opener=object(),
    )

    with pytest.raises(RuntimeError, match="authentication login URL"):
        clearer()


@pytest.mark.parametrize(
    ("cache_url", "login_url"),
    [
        (
            "http://127.0.0.1:8765/api/dashboard/cache/clear",
            "http://127.0.0.1:8765/api/auth/login",
        ),
        (
            "http://[::1]:8765/api/dashboard/cache/clear",
            "http://[::1]:8765/api/auth/login",
        ),
        (
            "http://127.0.0.1/api/dashboard/cache/clear",
            "http://127.0.0.1:80/api/auth/login",
        ),
        (
            "https://[::1]/api/dashboard/cache/clear",
            "https://[::1]:443/api/auth/login",
        ),
    ],
)
def test_dashboard_cache_clearer_accepts_ipv4_and_ipv6_loopback(cache_url, login_url):
    requests = []

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            return Response()

    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url=cache_url,
        login_url=login_url,
        username="admin",
        password="password",
        opener=Opener(),
    )

    clearer()

    assert requests == [login_url, cache_url]


def test_dashboard_cache_clearer_default_opener_disables_environment_proxies(monkeypatch):
    handlers = []

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, _request, timeout):
            return Response()

    def fake_build_opener(*selected_handlers):
        handlers.extend(selected_handlers)
        return Opener()

    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://attacker.invalid:8080")
    monkeypatch.setattr(eod_auto_repair, "build_opener", fake_build_opener)
    clearer = eod_auto_repair.build_dashboard_cache_clearer(
        cache_url="http://127.0.0.1:8765/api/dashboard/cache/clear",
    )

    clearer()

    assert handlers[0].proxies == {}


@pytest.mark.parametrize("redirect_phase", ["login", "cache"])
def test_dashboard_cache_clearer_rejects_redirect_without_forwarding_token(
    monkeypatch,
    redirect_phase,
):
    requests = []
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            requests.append((self.command, self.path, self.headers.get("X-Dashboard-Write-Token")))
            if self.path == (
                "/api/auth/login"
                if redirect_phase == "login"
                else "/api/dashboard/cache/clear"
            ):
                self.send_response(302)
                self.send_header("Location", "/redirected")
            else:
                self.send_response(204)
            self.end_headers()

        do_GET = _respond
        do_POST = _respond

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        clearer = eod_auto_repair.build_dashboard_cache_clearer(
            cache_url=(
                f"http://127.0.0.1:{server.server_port}/api/dashboard/cache/clear"
            ),
            login_url=f"http://127.0.0.1:{server.server_port}/api/auth/login",
            username="admin" if redirect_phase == "login" else "",
            password="password" if redirect_phase == "login" else "",
            write_token="redirect-secret",
        )

        with pytest.raises(RuntimeError, match="request failed"):
            clearer()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert requests == [
        (
            "POST",
            "/api/auth/login"
            if redirect_phase == "login"
            else "/api/dashboard/cache/clear",
            None if redirect_phase == "login" else "redirect-secret",
        )
    ]


def test_browser_acceptance_is_ordered_between_strategy_publish_and_downstream_presentation():
    loop_names = [
        name
        for name in eod_auto_repair.LOOP_REPAIR_ORDER
        if name
        in {
            "strategy_publish",
            "dashboard_browser_acceptance",
            "dashboard_surface_freshness",
            "ops_health",
        }
    ]
    presentation_names = next(
        names for stage, names in eod_auto_repair.STAGE_CHECKS if stage == "presentation"
    )
    presentation_gate_names = [
        name
        for name in presentation_names
        if name
        in {
            "dashboard_browser_acceptance",
            "dashboard_surface_freshness",
            "ops_health",
        }
    ]

    assert loop_names == [
        "strategy_publish",
        "dashboard_browser_acceptance",
        "dashboard_surface_freshness",
        "ops_health",
    ]
    assert presentation_gate_names == [
        "dashboard_surface_freshness",
        "ops_health",
    ]


def test_default_browser_action_uses_same_run_manifest_identities_and_verified_result(tmp_path):
    trade_date = "2026-07-20"
    run_id = "strategy-run-1"
    rows = _strategy_manifest_rows(trade_date=trade_date, run_id=run_id)
    candidates = [
        _browser_candidate(
            strategy_id,
            trade_date=trade_date,
            hour=index + 1,
            run_id=run_id,
        )
        for index, strategy_id in enumerate(BROWSER_STRATEGY_IDS)
    ]
    parsed_result = _verified_browser_result(
        tmp_path,
        candidates=candidates,
        trade_date=trade_date,
        run_id=run_id,
    )
    captured = {"runner": [], "manifest": []}
    cache_clearer = lambda: None

    def browser_runner(**kwargs):
        captured["runner"].append(kwargs)
        return parsed_result

    def browser_writer(result):
        assert result is parsed_result
        return write_browser_acceptance_manifest(
            result,
            manifest_upsert=captured["manifest"].append,
        )

    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=browser_runner,
        browser_manifest_writer=browser_writer,
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: rows,
        browser_cache_clearer=cache_clearer,
        browser_acceptance_enabled=True,
    )

    result = registry["dashboard_browser_acceptance"](trade_date, tmp_path)

    assert type(registry) is dict
    assert "dashboard_browser_acceptance" in dict(registry)
    assert len(captured["runner"]) == 1
    assert captured["runner"][0] == {
        "trade_date": trade_date,
        "run_id": run_id,
        "revision": "abc123",
        "output_dir": tmp_path / "browser-output" / trade_date / run_id,
        "candidate_publications": candidates,
        "cache_clearer": cache_clearer,
    }
    assert captured["manifest"][0]["run_id"] == run_id
    assert result.status == RepairStatus.SUCCESS
    assert result.artifact_paths == list(parsed_result.artifact_paths)
    assert result.validation_result["evidence"]["parsed_result"]["run_id"] == run_id
    assert result.validation_result["evidence"]["manifest"]["status"] == "success"


@pytest.mark.parametrize(
    ("first_failures", "failed_gate", "expected_clears", "expected_statuses"),
    [
        (
            ["stale_cache: old selector payload"],
            "runtime-deep-links",
            1,
            ["failed", "success"],
        ),
        (
            ["api_ui_mismatch: total return differs"],
            "candidate-consistency",
            0,
            ["failed"],
        ),
    ],
)
def test_default_browser_action_integration_applies_cache_repair_whitelist(
    tmp_path,
    first_failures,
    failed_gate,
    expected_clears,
    expected_statuses,
):
    trade_date = "2026-07-20"
    run_id = "strategy-run-1"
    rows = _strategy_manifest_rows(trade_date=trade_date, run_id=run_id)
    candidates = select_latest_strategy_candidate_publications(
        rows,
        trade_date=trade_date,
    )[1]
    commands = []
    cache_clears = []

    class FakeProcess:
        def __init__(self, kwargs, *, attempt):
            self.kwargs = kwargs
            self.attempt = attempt
            self.returncode = 1 if attempt == 1 else 0

        def wait(self, timeout):
            assert timeout > 0
            report_path = (
                Path(self.kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
                / "eod-browser-acceptance.json"
            )
            if self.attempt == 1:
                _write_browser_report(
                    report_path,
                    candidates=candidates,
                    trade_date=trade_date,
                    run_id=run_id,
                    status="failed",
                    failures=first_failures,
                    failed_gate=failed_gate,
                )
            else:
                _write_browser_report(
                    report_path,
                    candidates=candidates,
                    trade_date=trade_date,
                    run_id=run_id,
                )
            return self.returncode

    def popen(command, **kwargs):
        commands.append(command)
        return FakeProcess(kwargs, attempt=len(commands))

    def browser_runner(**kwargs):
        return run_browser_acceptance(
            **kwargs,
            previous_publications=_previous_browser_publications(candidates),
            popen=popen,
            runtime_checker=lambda _dashboard: None,
        )

    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=browser_runner,
        browser_manifest_writer=lambda result: {"status": result.status.value},
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: rows,
        browser_cache_clearer=lambda: cache_clears.append("cleared"),
        browser_acceptance_enabled=True,
    )

    result = registry["dashboard_browser_acceptance"](trade_date, tmp_path)

    assert cache_clears == ["cleared"] * expected_clears
    assert commands == [["pnpm", "test:e2e:eod"]] * len(expected_statuses)
    parsed = result.validation_result["evidence"]["parsed_result"]
    assert [attempt["status"] for attempt in parsed["attempts"]] == expected_statuses
    assert result.status == (
        RepairStatus.SUCCESS if expected_statuses[-1] == "success" else RepairStatus.FAILED
    )


def test_default_browser_action_integration_missing_cache_url_fails_infrastructure(
    monkeypatch,
    tmp_path,
):
    trade_date = "2026-07-20"
    run_id = "strategy-run-1"
    rows = _strategy_manifest_rows(trade_date=trade_date, run_id=run_id)
    candidates = select_latest_strategy_candidate_publications(
        rows,
        trade_date=trade_date,
    )[1]
    commands = []

    class FakeProcess:
        returncode = 1

        def __init__(self, kwargs):
            self.kwargs = kwargs

        def wait(self, timeout):
            assert timeout > 0
            _write_browser_report(
                Path(self.kwargs["env"]["PLAYWRIGHT_EOD_OUTPUT_DIR"])
                / "eod-browser-acceptance.json",
                candidates=candidates,
                trade_date=trade_date,
                run_id=run_id,
                status="failed",
                failures=["stale_cache: old selector payload"],
                failed_gate="runtime-deep-links",
            )
            return self.returncode

    def popen(command, **kwargs):
        commands.append(command)
        return FakeProcess(kwargs)

    def browser_runner(**kwargs):
        return run_browser_acceptance(
            **kwargs,
            previous_publications=_previous_browser_publications(candidates),
            popen=popen,
            runtime_checker=lambda _dashboard: None,
        )

    monkeypatch.delenv("DASHBOARD_CACHE_CLEAR_URL", raising=False)
    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=browser_runner,
        browser_manifest_writer=lambda result: {"status": result.status.value},
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: rows,
        browser_acceptance_enabled=True,
    )

    result = registry["dashboard_browser_acceptance"](trade_date, tmp_path)

    assert commands == [["pnpm", "test:e2e:eod"]]
    assert result.status == RepairStatus.FAILED
    assert result.metrics["failure_classes"] == ["infrastructure"]
    assert "cache clear URL missing" in result.message


def test_browser_result_payload_preserves_attempt_history():
    result = SimpleNamespace(
        status=RepairStatus.DEGRADED,
        attempts=(
            SimpleNamespace(
                attempt_number=1,
                status=RepairStatus.FAILED,
                duration_seconds=1.5,
                exit_code=1,
                failure_classes=("runtime",),
                warnings=(),
                artifact_paths=("attempt-1/trace.zip",),
                snapshot={"phase": "initial"},
                message="runtime retry",
            ),
            SimpleNamespace(
                attempt_number=2,
                status=RepairStatus.SUCCESS,
                duration_seconds=0.5,
                exit_code=0,
                failure_classes=(),
                warnings=(),
                artifact_paths=("attempt-2/trace.zip",),
                snapshot={"phase": "rerun"},
                message="rerun passed",
            ),
        ),
    )

    payload = eod_auto_repair._browser_result_payload(result)

    assert [attempt["attempt_number"] for attempt in payload["attempts"]] == [1, 2]
    assert payload["attempts"][0]["status"] == "failed"
    assert payload["attempts"][1]["message"] == "rerun passed"


@pytest.mark.parametrize("row_mutation", ["missing_strategy", "wrong_run"])
def test_default_browser_action_fails_closed_before_runner_for_invalid_candidate_identity(
    tmp_path,
    row_mutation,
):
    rows = _strategy_manifest_rows()
    if row_mutation == "missing_strategy":
        rows.pop()
    else:
        rows[-1]["run_id"] = "different-run"
    browser_calls = []
    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=lambda **kwargs: browser_calls.append(kwargs),
        browser_manifest_writer=lambda result: None,
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: rows,
        browser_acceptance_enabled=True,
    )

    result = registry["dashboard_browser_acceptance"]("2026-07-20", tmp_path)

    assert browser_calls == []
    assert result.status == RepairStatus.FAILED
    assert "candidate" in result.message
    assert "current EOD run" not in result.message


def test_plain_registry_independent_browser_calls_select_current_persisted_cohort(tmp_path):
    trade_date = "2026-07-20"
    rows = _strategy_manifest_rows(trade_date=trade_date, run_id="strategy-run-1")
    browser_run_ids = []

    def browser_runner(**kwargs):
        browser_run_ids.append(kwargs["run_id"])
        return _verified_browser_result(
            tmp_path / f"browser-call-{len(browser_run_ids)}",
            candidates=kwargs["candidate_publications"],
            trade_date=kwargs["trade_date"],
            run_id=kwargs["run_id"],
        )

    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=browser_runner,
        browser_manifest_writer=lambda result: {
            "run_id": result.run_id,
            "status": result.status.value,
        },
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: rows,
        browser_acceptance_enabled=True,
    )

    first = dict(registry)["dashboard_browser_acceptance"](trade_date, tmp_path / "run-1")
    assert first.status == RepairStatus.SUCCESS
    assert browser_run_ids == ["strategy-run-1"]

    rows = _strategy_manifest_rows(trade_date=trade_date, run_id="strategy-run-2")
    for index, row in enumerate(rows):
        row["started_at"] = f"{trade_date}T1{index + 1}:00:00+00:00"
        row["ended_at"] = row["started_at"]
    second = dict(registry)["dashboard_browser_acceptance"](trade_date, tmp_path / "run-2")

    assert second.status == RepairStatus.SUCCESS
    assert browser_run_ids == ["strategy-run-1", "strategy-run-2"]


def test_strategy_publish_persistence_makes_new_cohort_supersede_old_run(tmp_path):
    trade_date = "2026-07-20"
    old_rows = _strategy_manifest_rows(trade_date=trade_date, run_id="strategy-run-old")
    new_rows = _strategy_manifest_rows(trade_date=trade_date, run_id="strategy-run-new")
    for index, row in enumerate(old_rows):
        row["started_at"] = f"{trade_date}T0{index + 1}:00:00+00:00"
        row["ended_at"] = row["started_at"]
    for index, row in enumerate(new_rows):
        row["started_at"] = f"{trade_date}T1{index + 1}:00:00+00:00"
        row["ended_at"] = row["started_at"]
    persisted_rows = list(old_rows)
    browser_run_ids = []

    def strategy_publisher(**kwargs):
        persisted_rows.extend(new_rows)
        return {
            "run_id": "strategy-run-new",
            "output_dir": str(tmp_path / "strategy-run-new"),
            "review_rows": 3,
        }

    def browser_runner(**kwargs):
        browser_run_ids.append(kwargs["run_id"])
        return _verified_browser_result(
            tmp_path / "new-cohort-browser",
            candidates=kwargs["candidate_publications"],
            trade_date=kwargs["trade_date"],
            run_id=kwargs["run_id"],
        )

    registry = build_default_action_registry(
        output_root=tmp_path,
        browser_runner=browser_runner,
        browser_manifest_writer=lambda result: {
            "run_id": result.run_id,
            "status": result.status.value,
        },
        browser_revision="abc123",
        browser_output_root=tmp_path / "browser-output",
        browser_manifest_loader=lambda trade_date: persisted_rows,
        strategy_publisher=strategy_publisher,
        browser_acceptance_enabled=True,
    )

    publish_result = registry["strategy_publish"](trade_date, tmp_path)
    browser_result = registry["dashboard_browser_acceptance"](trade_date, tmp_path)

    assert publish_result.status == RepairStatus.SUCCESS
    assert browser_result.status == RepairStatus.SUCCESS
    assert browser_run_ids == ["strategy-run-new"]


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
    assert callable(captured["kwargs"]["progress"])
    assert captured["kwargs"]["symbol_sleep_seconds"] == 0.75


def test_default_minute5_action_refreshes_raw_and_qfq_quality(monkeypatch, tmp_path):
    captured = {}

    def fake_repair_minute5_raw_bars(_trade_date, **kwargs):
        captured.update(kwargs)
        return RepairActionResult("repair_minute5_raw_bars", RepairStatus.SUCCESS)

    monkeypatch.setattr(
        eod_auto_repair_actions,
        "repair_minute5_raw_bars",
        fake_repair_minute5_raw_bars,
    )
    monkeypatch.setattr(
        daily_close_pipeline,
        "load_minute5_expected_ts_codes",
        lambda _service, _trade_date: ["600000.SH"],
    )
    inspected = []
    monkeypatch.setattr(
        daily_close_pipeline,
        "inspect_minute5_quality_from_db",
        lambda _service, _codes, _trade_date, *, adjust_type="raw": inspected.append(
            adjust_type
        )
        or {
            "status": "pass",
            "expected_count": 1,
            "actual_count": 1,
            "missing_symbols": [],
            "abnormal_symbols": [],
            "check_summary": f"{adjust_type} pass",
        },
    )
    persisted = []
    monkeypatch.setattr(
        daily_close_pipeline,
        "upsert_quality",
        lambda **kwargs: persisted.append(kwargs["dataset_name"]),
    )

    build_default_action_registry(output_root="outputs")["minute5_bars"](
        "2026-07-10", tmp_path
    )
    result = captured["quality_refresher"]("test", date(2026, 7, 10))

    assert inspected == ["raw", "qfq"]
    assert persisted == ["minute5_bar", "minute5_qfq_bar"]
    assert result["raw"]["status"] == "pass"
    assert result["qfq"]["status"] == "pass"


def test_repair_minute5_raw_bars_persists_each_symbol_before_later_interrupt(monkeypatch):
    monkeypatch.setattr(eod_auto_repair_actions.time, "sleep", lambda _seconds: None)
    upserted_batches = []

    def fake_fetcher(ts_code, start_date, end_date, timeout_seconds):
        if ts_code == "000001.SZ":
            raise KeyboardInterrupt("external timeout")
        return [
            {
                "ts_code": ts_code,
                "adjust_type": "raw",
                "trade_date": start_date,
            }
        ]

    def fake_upserter(_service, rows):
        upserted_batches.append(list(rows))
        return len(rows)

    with pytest.raises(KeyboardInterrupt):
        eod_auto_repair_actions.repair_minute5_raw_bars(
            "2026-07-09",
            service="test",
            missing_symbols_loader=lambda _trade_date: ["600000.SH", "000001.SZ"],
            raw_fetcher=fake_fetcher,
            upserter=fake_upserter,
            qfq_deriver=lambda _service, _trade_date: {"inserted_rows": 0},
            quality_refresher=lambda _service, _trade_date: {},
        )

    assert [[row["ts_code"] for row in batch] for batch in upserted_batches] == [["600000.SH"]]


def test_repair_minute5_raw_bars_rederives_qfq_when_raw_has_no_missing_symbols():
    qfq_calls = []
    quality_calls = []

    result = eod_auto_repair_actions.repair_minute5_raw_bars(
        "2026-07-10",
        service="test",
        missing_symbols_loader=lambda _trade_date: [],
        raw_fetcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("raw-complete repair must not fetch remotely")
        ),
        upserter=lambda *_args, **_kwargs: 0,
        qfq_deriver=lambda service, trade_date: qfq_calls.append(
            (service, trade_date)
        )
        or {"inserted_rows": 48},
        quality_refresher=lambda service, trade_date: quality_calls.append(
            (service, trade_date)
        )
        or {
            "raw": {
                "status": "pass",
                "expected_count": 1,
                "actual_count": 1,
                "missing_symbols": [],
                "abnormal_symbols": [],
            },
            "qfq": {
                "status": "pass",
                "expected_count": 1,
                "actual_count": 1,
                "missing_symbols": [],
                "abnormal_symbols": [],
            },
        },
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["attempted"] == 0
    assert result.metrics["qfq_rows"] == 48
    assert qfq_calls == [("test", date(2026, 7, 10))]
    assert quality_calls == [("test", date(2026, 7, 10))]


def test_repair_minute5_raw_bars_emits_progress_events(monkeypatch):
    monkeypatch.setattr(eod_auto_repair_actions.time, "sleep", lambda _seconds: None)
    events = []

    def fake_fetcher(ts_code, start_date, end_date, timeout_seconds):
        return [
            {
                "ts_code": ts_code,
                "adjust_type": "raw",
                "trade_date": start_date,
            }
        ]

    result = eod_auto_repair_actions.repair_minute5_raw_bars(
        "2026-07-09",
        service="test",
        missing_symbols_loader=lambda _trade_date: ["600000.SH", "000001.SZ"],
        raw_fetcher=fake_fetcher,
        upserter=lambda _service, rows: len(rows),
        qfq_deriver=lambda _service, _trade_date: {"inserted_rows": 2},
        quality_refresher=lambda _service, _trade_date: {
            "expected_count": 2,
            "actual_count": 2,
            "missing_symbols": [],
            "abnormal_symbols": [],
        },
        progress=events.append,
    )

    assert result.status == RepairStatus.SUCCESS
    assert [event["event"] for event in events] == [
        "minute5_raw_repair_started",
        "minute5_raw_repair_progress",
        "minute5_raw_repair_progress",
        "minute5_raw_repair_completed",
    ]
    assert events[-1]["completed"] == 2
    assert events[-1]["total"] == 2
    assert events[-1]["rows"] == 2


def test_repair_minute5_raw_bars_refreshes_quality_at_progress_checkpoint(monkeypatch):
    monkeypatch.setattr(eod_auto_repair_actions.time, "sleep", lambda _seconds: None)
    quality_refreshes = []
    symbols = [f"60{i:04d}.SH" for i in range(50)] + ["000001.SZ"]

    def fake_fetcher(ts_code, start_date, end_date, timeout_seconds):
        if ts_code == "000001.SZ":
            raise KeyboardInterrupt("external timeout")
        return [
            {
                "ts_code": ts_code,
                "adjust_type": "raw",
                "trade_date": start_date,
            }
        ]

    with pytest.raises(KeyboardInterrupt):
        eod_auto_repair_actions.repair_minute5_raw_bars(
            "2026-07-09",
            service="test",
            missing_symbols_loader=lambda _trade_date: symbols,
            raw_fetcher=fake_fetcher,
            upserter=lambda _service, rows: len(rows),
            qfq_deriver=lambda _service, _trade_date: {"inserted_rows": 0},
            quality_refresher=lambda service, trade_date: quality_refreshes.append((service, trade_date)) or {},
        )

    assert quality_refreshes == [("test", date(2026, 7, 9))]


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
