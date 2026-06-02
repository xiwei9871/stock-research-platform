import pandas as pd
import pytest

from stock_research.factor_eval import multi_horizon
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


def test_generate_multi_horizon_report_reuses_turnover_across_horizons(monkeypatch):
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
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
    turnover_calls = []
    report_calls = []
    fake_turnover = pd.DataFrame(
        [{"trade_date": "2026-01-01", "previous_trade_date": None, "top_n": 2, "overlap_count": 0, "turnover": None}]
    )

    monkeypatch.setattr(
        multi_horizon,
        "calc_factor_turnover",
        lambda factors, factor_col="factor_value", top_n=20: turnover_calls.append(
            {"factor_col": factor_col, "top_n": top_n, "rows": len(factors)}
        )
        or fake_turnover,
        raising=False,
    )
    monkeypatch.setattr(
        multi_horizon,
        "generate_factor_eval_report",
        lambda factors, returns, factor_name, factor_col="factor_value", return_col="forward_return_5d", quantiles=5, top_n=20, turnover_frame=None, merged_frame=None: report_calls.append(
            {
                "return_col": return_col,
                "turnover_frame": turnover_frame,
                "merged_frame": merged_frame,
            }
        )
        or {
            "factor_name": factor_name,
            "return_col": return_col,
            "turnover": turnover_frame,
            "ic_summary": {},
            "rank_ic_summary": {},
        },
    )

    result = multi_horizon.generate_multi_horizon_report(
        factors=factors,
        returns=returns,
        factor_name="demo_factor",
        horizons=[5, 10],
        top_n=2,
    )

    assert result["reports"][5]["turnover"] is fake_turnover
    assert result["reports"][10]["turnover"] is fake_turnover
    assert turnover_calls == [{"factor_col": "factor_value", "top_n": 2, "rows": 2}]
    assert [call["turnover_frame"] is fake_turnover for call in report_calls] == [True, True]


def test_generate_multi_horizon_report_prepares_inputs_once_and_merges_per_horizon(monkeypatch):
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
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
    prepared_factor_calls = []
    prepared_return_calls = []
    merge_calls = []
    report_calls = []
    prepared_factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
    prepared_returns = pd.DataFrame(
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
    fake_turnover = pd.DataFrame(
        [{"trade_date": "2026-01-01", "previous_trade_date": None, "top_n": 2, "overlap_count": 0, "turnover": None}]
    )

    def fake_merge(prepared_factor_frame, prepared_return_frame, factor_col, return_col):
        merge_calls.append(
            {
                "factor_rows": len(prepared_factor_frame),
                "return_rows": len(prepared_return_frame),
                "factor_col": factor_col,
                "return_col": return_col,
            }
        )
        return pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "A",
                    "factor_value": 1.0,
                    return_col: 0.01,
                }
            ]
        )

    monkeypatch.setattr(
        multi_horizon,
        "prepare_factor_frame",
        lambda factors, factor_col="factor_value": prepared_factor_calls.append(
            {"rows": len(factors), "factor_col": factor_col}
        )
        or prepared_factors,
        raising=False,
    )
    monkeypatch.setattr(
        multi_horizon,
        "prepare_return_frame",
        lambda returns, return_cols=None: prepared_return_calls.append(
            {"rows": len(returns), "return_cols": list(return_cols or [])}
        )
        or prepared_returns,
        raising=False,
    )
    monkeypatch.setattr(
        multi_horizon,
        "merge_prepared_factor_returns",
        fake_merge,
        raising=False,
    )
    monkeypatch.setattr(
        multi_horizon,
        "calc_factor_turnover",
        lambda factors, factor_col="factor_value", top_n=20: fake_turnover,
        raising=False,
    )
    monkeypatch.setattr(
        multi_horizon,
        "generate_factor_eval_report",
        lambda factors, returns, factor_name, factor_col="factor_value", return_col="forward_return_5d", quantiles=5, top_n=20, turnover_frame=None, merged_frame=None: report_calls.append(
            {"return_col": return_col, "turnover_frame": turnover_frame, "merged_frame": merged_frame}
        )
        or {
            "factor_name": factor_name,
            "return_col": return_col,
            "turnover": turnover_frame,
            "ic_summary": {},
            "rank_ic_summary": {},
        },
    )

    result = multi_horizon.generate_multi_horizon_report(
        factors=factors,
        returns=returns,
        factor_name="demo_factor",
        horizons=[5, 10],
        top_n=2,
    )

    assert result["reports"][5]["turnover"] is fake_turnover
    assert prepared_factor_calls == [{"rows": 2, "factor_col": "factor_value"}]
    assert prepared_return_calls == [
        {"rows": 2, "return_cols": ["forward_return_5d", "forward_return_10d"]}
    ]
    assert [call["return_col"] for call in merge_calls] == [
        "forward_return_5d",
        "forward_return_10d",
    ]
    assert [call["turnover_frame"] is fake_turnover for call in report_calls] == [True, True]
    assert [call["merged_frame"] is not None for call in report_calls] == [True, True]
