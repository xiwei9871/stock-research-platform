import pandas as pd
import pytest

from stock_research.factor_eval import ic, quantile_return, report, turnover


def test_calc_ic_and_rank_ic_by_trade_date():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 1.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": -0.01},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.00},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.01},
        ]
    )

    ic_frame = ic.calc_ic(factors, returns, return_col="forward_return_5d")
    rank_ic_frame = ic.calc_rank_ic(factors, returns, return_col="forward_return_5d")
    summary = ic.summarize_ic(ic_frame)

    assert list(ic_frame["ic"].round(6)) == [1.0, -1.0]
    assert list(rank_ic_frame["rank_ic"].round(6)) == [1.0, -1.0]
    assert summary["mean_ic"] == pytest.approx(0.0)
    assert summary["ic_count"] == 2


def test_calc_quantile_return_groups_by_date_without_cross_date_leakage():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 1.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.30},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.40},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.50},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.40},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.01},
        ]
    )

    result = quantile_return.calc_quantile_return(
        factors,
        returns,
        return_col="forward_return_5d",
        quantiles=2,
    )

    top = result[result["quantile"] == 2]
    bottom = result[result["quantile"] == 1]
    assert list(top["mean_return"].round(3)) == [0.35, 0.45]
    assert list(bottom["mean_return"].round(3)) == [0.015, 0.015]

    spread = quantile_return.calc_top_bottom_spread(result)
    assert list(spread["top_bottom_spread"].round(3)) == [0.335, 0.435]


def test_calc_factor_turnover_tracks_top_n_membership_changes():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 5.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 4.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 5.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 3.0},
            {"trade_date": "2026-01-03", "asset_id": "E", "factor_value": 5.0},
            {"trade_date": "2026-01-03", "asset_id": "F", "factor_value": 4.0},
            {"trade_date": "2026-01-03", "asset_id": "A", "factor_value": 3.0},
        ]
    )

    result = turnover.calc_factor_turnover(factors, top_n=2)

    assert result.to_dict("records") == [
        {
            "trade_date": "2026-01-02",
            "previous_trade_date": "2026-01-01",
            "top_n": 2,
            "overlap_count": 1,
            "turnover": 0.5,
        },
        {
            "trade_date": "2026-01-03",
            "previous_trade_date": "2026-01-02",
            "top_n": 2,
            "overlap_count": 0,
            "turnover": 1.0,
        },
    ]


def test_generate_factor_eval_report_returns_core_sections():
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
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.04},
        ]
    )

    result = report.generate_factor_eval_report(
        factors,
        returns,
        factor_name="demo_factor",
        return_col="forward_return_5d",
        quantiles=2,
        top_n=2,
    )

    assert result["factor_name"] == "demo_factor"
    assert result["return_col"] == "forward_return_5d"
    assert result["ic_summary"]["mean_ic"] == pytest.approx(1.0)
    assert not result["quantile_return"].empty
    assert not result["turnover"].empty
