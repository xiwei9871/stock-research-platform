from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairLoopCycleResult,
    RepairRunSummary,
    RepairStageResult,
    RepairStatus,
)
from stock_research.eod_auto_repair import _write_summary_files


def test_repair_summary_preserves_legacy_positional_field_order():
    checks = [RepairCheckResult("ops_health", RepairStatus.SUCCESS, "ready")]

    summary = RepairRunSummary(
        "2026-07-20",
        "check",
        RepairStatus.SUCCESS,
        checks,
    )

    assert summary.checks_before == checks
    assert summary.run_id == ""


def test_repair_summary_serializes_nested_results():
    summary = RepairRunSummary(
        trade_date="2026-06-29",
        mode="repair",
        final_status=RepairStatus.SUCCESS,
        run_id="eod-model-test",
        checks_before=[
            RepairCheckResult(
                name="lhb_features",
                status=RepairStatus.FAILED,
                message="missing",
                metrics={"row_count": 0},
            )
        ],
        actions=[
            RepairActionResult(
                name="build_lhb_features",
                status=RepairStatus.SUCCESS,
                message="built",
                metrics={"row_count": 102},
                artifact_paths=[
                    "outputs/research/strategy_daily_eod/2026-06-29/lhb_event_features_daily_sample.csv"
                ],
            )
        ],
        checks_after=[
            RepairCheckResult(
                name="lhb_features",
                status=RepairStatus.SUCCESS,
                message="ready",
                metrics={"row_count": 102},
            )
        ],
    )

    payload = summary.to_dict()
    assert payload["run_id"] == "eod-model-test"

    assert payload["trade_date"] == "2026-06-29"
    assert payload["final_status"] == "success"
    assert payload["checks_before"][0]["metrics"]["row_count"] == 0
    assert payload["actions"][0]["artifact_paths"][0].endswith("lhb_event_features_daily_sample.csv")


def test_repair_summary_exposes_final_browser_check_and_action_without_new_canonical_state():
    summary = RepairRunSummary(
        trade_date="2026-07-20",
        mode="loop",
        final_status=RepairStatus.DEGRADED,
        checks_before=[
            RepairCheckResult(
                "dashboard_browser_acceptance",
                RepairStatus.FAILED,
                "missing",
                blocker=True,
            )
        ],
        actions=[
            RepairActionResult(
                "dashboard_browser_acceptance",
                RepairStatus.DEGRADED,
                "publishable warnings",
                artifact_paths=["/tmp/eod-browser-acceptance.json"],
                validation_result={
                    "component": "dashboard_browser_acceptance",
                    "evidence": {"run_id": "strategy-eod-2026-07-20-local"},
                },
            )
        ],
        checks_after=[
            RepairCheckResult(
                "dashboard_browser_acceptance",
                RepairStatus.DEGRADED,
                "publishable warnings",
                metrics={"warnings": ["console warning"]},
            )
        ],
    )

    payload = summary.to_dict()

    assert payload["browser_acceptance"] == {
        "check": payload["checks_after"][0],
        "action": payload["actions"][0],
    }
    assert set(summary.__dataclass_fields__) == {
        "trade_date",
        "mode",
        "final_status",
        "run_id",
        "checks_before",
        "actions",
        "checks_after",
        "stages",
        "loop_cycles",
        "remaining_blockers",
        "remaining_non_blockers",
        "next_actions",
        "initial_classification",
        "final_classification",
        "loop_stop_reason",
        "dry_run",
        "max_cycles",
        "warnings",
        "infrastructure_issues",
        "recommended_followups",
    }


def test_repair_summary_keeps_latest_known_browser_check_when_recheck_plan_fails():
    browser = RepairCheckResult(
        "dashboard_browser_acceptance",
        RepairStatus.SUCCESS,
        "ready",
        metrics={"run_id": "strategy-run-1"},
    )
    summary = RepairRunSummary(
        trade_date="2026-07-20",
        mode="loop",
        final_status=RepairStatus.FAILED,
        checks_before=[browser],
        checks_after=[
            RepairCheckResult(
                "check_plan",
                RepairStatus.FAILED,
                "database unavailable",
                blocker=True,
            )
        ],
    )

    payload = summary.to_dict()

    assert payload["browser_acceptance"]["check"] == browser.to_dict()


def test_repair_summary_serializes_stages_and_remaining_issues():
    summary = RepairRunSummary(
        trade_date="2026-07-01",
        mode="repair",
        final_status=RepairStatus.DEGRADED,
        stages=[
            RepairStageResult(
                name="base_bars",
                checks_before=[
                    RepairCheckResult(
                        "minute5_bars",
                        RepairStatus.FAILED,
                        "minute5 missing",
                        blocker=True,
                    )
                ],
                actions=[
                    RepairActionResult(
                        "repair_minute5_bars",
                        RepairStatus.SUCCESS,
                        "minute5 repaired",
                    )
                ],
                checks_after=[
                    RepairCheckResult("minute5_bars", RepairStatus.SUCCESS, "ready")
                ],
                remaining_blockers=[],
            )
        ],
        remaining_blockers=[],
        remaining_non_blockers=["reports"],
        next_actions=["Generate reports for 2026-07-01"],
    )

    payload = summary.to_dict()

    assert payload["stages"][0]["name"] == "base_bars"
    assert payload["remaining_non_blockers"] == ["reports"]
    assert payload["next_actions"] == ["Generate reports for 2026-07-01"]


def test_run_report_includes_loop_observability_fields(tmp_path):
    summary = RepairRunSummary(
        trade_date="2026-07-01",
        mode="loop",
        final_status=RepairStatus.DEGRADED,
        checks_before=[RepairCheckResult("factor_daily", RepairStatus.FAILED, "missing", blocker=True)],
        checks_after=[RepairCheckResult("factor_daily", RepairStatus.SUCCESS, "ready")],
        actions=[
            RepairActionResult(
                "repair_factor_daily",
                RepairStatus.SUCCESS,
                "fixed",
                started_at="2026-07-02T01:00:00+00:00",
                ended_at="2026-07-02T01:00:03+00:00",
                exit_code=0,
                validation_result={"component": "factor_daily", "status": "success"},
            )
        ],
        loop_cycles=[
            RepairLoopCycleResult(
                cycle_number=1,
                actions=[
                    RepairActionResult(
                        "repair_factor_daily",
                        RepairStatus.SUCCESS,
                        "fixed",
                        started_at="2026-07-02T01:00:00+00:00",
                        ended_at="2026-07-02T01:00:03+00:00",
                        exit_code=0,
                        validation_result={"component": "factor_daily", "status": "success"},
                    )
                ],
            )
        ],
        initial_classification={"factor_daily": "blocker"},
        final_classification={"factor_daily": "healthy"},
        loop_stop_reason="ready_with_no_blockers",
        warnings=["no repair action registered for blocker dashboard_surface_freshness"],
        infrastructure_issues=["lock_mode=python_lockfile"],
    )

    _write_summary_files(summary, tmp_path)

    report = (tmp_path / "run_report.md").read_text()
    assert "Report path:" in report
    assert "Initial status:" in report
    assert "started=2026-07-02T01:00:00+00:00" in report
    assert "exit_code=0" in report
    assert "validation=" in report
    assert "## Warnings" in report
    assert "## Infrastructure issues" in report
