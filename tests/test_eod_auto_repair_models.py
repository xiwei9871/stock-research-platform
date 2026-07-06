from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairLoopCycleResult,
    RepairRunSummary,
    RepairStageResult,
    RepairStatus,
)
from stock_research.eod_auto_repair import _write_summary_files


def test_repair_summary_serializes_nested_results():
    summary = RepairRunSummary(
        trade_date="2026-06-29",
        mode="repair",
        final_status=RepairStatus.SUCCESS,
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

    assert payload["trade_date"] == "2026-06-29"
    assert payload["final_status"] == "success"
    assert payload["checks_before"][0]["metrics"]["row_count"] == 0
    assert payload["actions"][0]["artifact_paths"][0].endswith("lhb_event_features_daily_sample.csv")


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
