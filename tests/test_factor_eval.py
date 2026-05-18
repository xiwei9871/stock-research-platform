import pandas as pd
import pytest
from pandas.api.types import is_numeric_dtype

from stock_research.factor_eval import ic, quantile_return, report, turnover
from stock_research.factor_eval import base as factor_eval_base


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


def test_calc_quantile_return_handles_duplicate_bin_edges_without_crashing():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "E", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "F", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "G", "factor_value": 4.0},
            {"trade_date": "2026-01-01", "asset_id": "H", "factor_value": 5.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04},
            {"trade_date": "2026-01-01", "asset_id": "E", "forward_return_5d": 0.05},
            {"trade_date": "2026-01-01", "asset_id": "F", "forward_return_5d": 0.06},
            {"trade_date": "2026-01-01", "asset_id": "G", "forward_return_5d": 0.07},
            {"trade_date": "2026-01-01", "asset_id": "H", "forward_return_5d": 0.08},
        ]
    )

    result = quantile_return.calc_quantile_return(
        factors,
        returns,
        return_col="forward_return_5d",
        quantiles=5,
    )

    assert not result.empty
    assert set(result["quantile"]) <= {1, 2, 3, 4, 5}


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


def test_generate_factor_eval_report_merges_factor_returns_once(monkeypatch):
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
        ]
    )
    merged_calls = []
    merged_frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "factor_value": 1.0,
                "forward_return_5d": 0.01,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "factor_value": 2.0,
                "forward_return_5d": 0.02,
            },
        ]
    )
    expected_ic = pd.DataFrame([{"trade_date": "2026-01-01", "ic": 1.0, "n": 2}])
    expected_rank_ic = pd.DataFrame(
        [{"trade_date": "2026-01-01", "rank_ic": 1.0, "n": 2}]
    )
    expected_quantile = pd.DataFrame(
        [{"trade_date": "2026-01-01", "quantile": 1, "mean_return": 0.01, "count": 1}]
    )
    expected_turnover = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "previous_trade_date": None,
                "top_n": 2,
                "overlap_count": 0,
                "turnover": None,
            }
        ]
    )

    monkeypatch.setattr(
        report,
        "merged_factor_returns",
        lambda *args, **kwargs: merged_calls.append((args, kwargs)) or merged_frame,
        raising=False,
    )
    expected_merged = merged_frame
    monkeypatch.setattr(
        report.ic,
        "calc_ic",
        lambda factors, returns, factor_col="factor_value", return_col="forward_return_5d", merged_frame=None: (
            expected_ic
            if merged_frame is expected_merged
            else (_ for _ in ()).throw(AssertionError("calc_ic should receive merged_frame"))
        ),
    )
    monkeypatch.setattr(
        report.ic,
        "calc_rank_ic",
        lambda factors, returns, factor_col="factor_value", return_col="forward_return_5d", merged_frame=None: (
            expected_rank_ic
            if merged_frame is expected_merged
            else (_ for _ in ()).throw(
                AssertionError("calc_rank_ic should receive merged_frame")
            )
        ),
    )
    monkeypatch.setattr(
        report.quantile_return,
        "calc_quantile_return",
        lambda factors, returns, factor_col="factor_value", return_col="forward_return_5d", quantiles=5, merged_frame=None: (
            expected_quantile
            if merged_frame is expected_merged
            else (_ for _ in ()).throw(
                AssertionError("calc_quantile_return should receive merged_frame")
            )
        ),
    )
    monkeypatch.setattr(
        report.turnover,
        "calc_factor_turnover",
        lambda factors, factor_col="factor_value", top_n=20: expected_turnover,
    )

    result = report.generate_factor_eval_report(
        factors,
        returns,
        factor_name="demo_factor",
        return_col="forward_return_5d",
        quantiles=2,
        top_n=2,
    )

    assert len(merged_calls) == 1
    assert result["ic"] is expected_ic
    assert result["rank_ic"] is expected_rank_ic
    assert result["quantile_return"] is expected_quantile


def test_prepare_return_frame_skips_to_numeric_for_already_numeric_columns(monkeypatch):
    returns = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "forward_return_5d": 0.01,
                "forward_return_10d": 0.02,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "forward_return_5d": 0.02,
                "forward_return_10d": 0.03,
            },
        ]
    )
    to_numeric_calls = []
    original_to_numeric = factor_eval_base.pd.to_numeric

    def fail_if_called(series, *args, **kwargs):
        to_numeric_calls.append(series.name)
        return original_to_numeric(series, *args, **kwargs)

    monkeypatch.setattr(factor_eval_base.pd, "to_numeric", fail_if_called)

    result = factor_eval_base.prepare_return_frame(
        returns,
        return_cols=["forward_return_5d", "forward_return_10d"],
    )

    assert to_numeric_calls == []
    assert is_numeric_dtype(result["forward_return_5d"])
    assert is_numeric_dtype(result["forward_return_10d"])
