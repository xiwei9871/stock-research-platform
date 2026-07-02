from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
    RepairStageResult,
    RepairStatus,
)


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
