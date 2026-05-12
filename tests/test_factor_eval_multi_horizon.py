import pandas as pd
import pytest

from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report


def test_generate_multi_horizon_report_runs_each_return_column():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 4.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01, "forward_return_10d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02, "forward_return_10d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03, "forward_return_10d": 0.04},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04, "forward_return_10d": 0.05},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.01, "forward_return_10d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.02, "forward_return_10d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.03, "forward_return_10d": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.04, "forward_return_10d": 0.05},
        ]
    )

    result = generate_multi_horizon_report(
        factors,
        returns,
        factor_name="demo_factor",
        horizons=[5, 10],
        quantiles=2,
        top_n=2,
    )

    assert set(result["horizons"]) == {5, 10}
    assert result["reports"][5]["ic_summary"]["mean_ic"] == pytest.approx(1.0)
    assert result["reports"][10]["return_col"] == "forward_return_10d"
