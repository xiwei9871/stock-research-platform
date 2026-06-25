import pandas as pd

from stock_research.mid_trend_soft_ownership_v1 import (
    DEFAULT_SOFT_OWNERSHIP_END_DATE,
    DEFAULT_SOFT_OWNERSHIP_START_DATE,
    MidTrendSoftOwnershipConfig,
    default_soft_ownership_configs,
)


def test_default_window_is_fixed_full_experiment_window() -> None:
    assert DEFAULT_SOFT_OWNERSHIP_START_DATE == "2025-01-01"
    assert DEFAULT_SOFT_OWNERSHIP_END_DATE == "2026-06-12"


def test_default_soft_ownership_configs_expose_required_variants() -> None:
    configs = default_soft_ownership_configs()
    assert set(configs) == {
        "baseline",
        "entry_soft_weight_v1",
        "ownership_hold_v1",
        "partial_exit_v1",
        "combined_soft_ownership_v1",
    }
    assert configs["baseline"].variant_name == "baseline"
    assert configs["combined_soft_ownership_v1"].start_date == "2025-01-01"
    assert isinstance(configs["baseline"], MidTrendSoftOwnershipConfig)
    assert pd.isna(pd.Series([None], dtype=object).iloc[0])


def test_compare_baseline_to_reference_reports_series_and_row_count_diffs(
    tmp_path,
) -> None:
    from stock_research.mid_trend_soft_ownership_v1 import compare_baseline_to_reference

    rerun = {
        "equity": pd.DataFrame(
            [
                {"trade_date": "2025-01-02", "equity": 1.00},
                {"trade_date": "2025-01-03", "equity": 1.01},
            ]
        ),
        "holdings": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]),
        "trades": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]),
        "summary": pd.DataFrame(
            [
                {
                    "strategy_family": "current_mid_trend_strategy_v1",
                    "total_return": 0.01,
                    "max_drawdown": -0.02,
                }
            ]
        ),
    }
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "equity": 1.00},
            {"trade_date": "2025-01-03", "equity": 1.02},
        ]
    ).to_csv(reference_dir / "current_mid_trend_strategy_v1_equity.csv", index=False)
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]).to_csv(
        reference_dir / "current_mid_trend_strategy_v1_daily_holdings.csv",
        index=False,
    )
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]).to_csv(
        reference_dir / "current_mid_trend_strategy_v1_trade_changes.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "strategy_family": "current_mid_trend_strategy_v1",
                "total_return": 0.02,
                "max_drawdown": -0.02,
            }
        ]
    ).to_csv(reference_dir / "current_mid_trend_strategy_v1_summary.csv", index=False)

    report = compare_baseline_to_reference(rerun, reference_dir=reference_dir)

    assert report["baseline_match"] is False
    assert float(report["final_equity_diff"]) != 0.0
    assert "equity_series_max_abs_diff" in report
