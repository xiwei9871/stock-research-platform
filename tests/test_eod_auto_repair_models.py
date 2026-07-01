from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
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
