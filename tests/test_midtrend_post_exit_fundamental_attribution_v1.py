from pathlib import Path

import pandas as pd
from stock_research import cli


def _price_frame() -> pd.DataFrame:
    rows = []
    prices = {
        "A": [10, 11, 12, 13, 14],
        "B": [10, 9.8, 9.6, 9.4, 9.2],
        "C": [10, 10.1, 10.0, 10.4, 10.8],
    }
    dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    for asset_id, values in prices.items():
        for trade_date, close in zip(dates, values, strict=True):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def _funnel_frame() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ranks = {
        "2025-01-02": {"A": 1, "B": 2, "C": 3},
        "2025-01-03": {"A": 6, "B": 2, "C": 1},
        "2025-01-06": {"A": 8, "B": 4, "C": 1},
        "2025-01-07": {"A": 2, "B": 15, "C": 5},
        "2025-01-08": {"A": 1, "B": 16, "C": 7},
    }
    for trade_date in dates:
        for asset_id, rank in ranks[trade_date].items():
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "stock_name": asset_id,
                    "industry_name": "Tech",
                    "score_rank": rank,
                    "rank": rank,
                    "shadow_top10_rank": rank,
                    "score_total": 120 - rank,
                    "mid_trend_funnel_score": 120 - rank,
                    "mid_trend_layer": "stable_trend_watch" if asset_id != "B" else "high_elasticity_watch",
                    "mainline_status": "sustained_mainline" if asset_id != "B" else "neutral",
                    "industry_mainline_score_v1": 0.9 if asset_id != "B" else 0.4,
                    "ret_20_score": 90 if asset_id != "B" else 60,
                    "ret_60_score": 88 if asset_id != "B" else 55,
                    "ma20_slope_score": 85,
                    "ma60_slope_score": 83,
                    "trend_r2_20_score": 82,
                    "stock_excess_ret_20_score": 88 if asset_id != "B" else 58,
                    "sector_ret_20_score": 75,
                    "max_drawdown_20_score": 80 if asset_id != "B" else 45,
                    "volatility_20_score": 70,
                    "atr_pct_score": 65,
                    "technical_confirmed": asset_id != "B",
                    "mainline_confirmed": asset_id != "B",
                    "fundamental_quality_bucket": "quality_strong" if asset_id == "A" else ("quality_weak" if asset_id == "B" else "quality_unknown"),
                    "fundamental_quality_score": 85 if asset_id == "A" else (30 if asset_id == "B" else None),
                    "fundamental_confirmed": asset_id == "A",
                    "midtrend_confirmation_state": "T1_M1_F1" if asset_id == "A" else ("T0_M0_F0" if asset_id == "B" else "T1_M1_UNKNOWN_F"),
                    "fundamental_risk_flag": asset_id == "B",
                    "revenue_growth_yoy": 35 if asset_id == "A" else (-10 if asset_id == "B" else None),
                    "profit_growth_yoy": 28 if asset_id == "A" else (-15 if asset_id == "B" else None),
                    "roe": 18 if asset_id == "A" else (4 if asset_id == "B" else None),
                }
            )
    return pd.DataFrame(rows)


def _trades_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "previous_trade_date": "2025-01-02",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "action": "sell",
                "previous_weight": 0.1,
                "target_weight": 0.0,
                "delta_weight": -0.1,
                "confirmed_regime_state": "bull_trend",
                "mid_trend_funnel_score": 114,
                "score_rank": 6,
                "mid_trend_layer": "stable_trend_watch",
                "protection_reason": "",
            },
            {
                "trade_date": "2025-01-03",
                "previous_trade_date": "2025-01-02",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "action": "buy",
                "previous_weight": 0.0,
                "target_weight": 0.1,
                "delta_weight": 0.1,
                "confirmed_regime_state": "bull_trend",
                "mid_trend_funnel_score": 118,
                "score_rank": 2,
                "mid_trend_layer": "high_elasticity_watch",
                "protection_reason": "",
            },
        ]
    )


def _holdings_frame(strategy_family: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "strategy_family": strategy_family,
                "stock_name": "A",
                "industry_name": "Tech",
                "target_weight": 0.1,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "strategy_family": strategy_family,
                "stock_name": "B",
                "industry_name": "Tech",
                "target_weight": 0.1,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "strategy_family": strategy_family,
                "stock_name": "B",
                "industry_name": "Tech",
                "target_weight": 0.1,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "C",
                "strategy_family": strategy_family,
                "stock_name": "C",
                "industry_name": "Tech",
                "target_weight": 0.1,
            },
        ]
    )


def test_path_classification_and_unknown_fundamental_bucket() -> None:
    from stock_research.midtrend_post_exit_fundamental_attribution_v1 import (
        classify_post_exit_path,
        compute_fundamental_buckets,
    )

    row = pd.Series(
        {
            "forward_return_10d": 0.03,
            "forward_return_20d": 0.09,
            "forward_return_30d": 0.16,
            "forward_return_60d": 0.18,
            "max_drawdown_after_exit_10d": -0.02,
            "reentered_top10_within_30d": True,
            "reconfirmed_T1_M1_within_30d": True,
        }
    )
    assert classify_post_exit_path(row)["path_class"] in {"immediate_continuation", "pullback_then_reacceleration"}

    buckets = compute_fundamental_buckets(pd.Series({"revenue_growth_yoy": None, "profit_growth_yoy": None, "roe": None}))
    assert buckets["fundamental_quality_bucket"] == "quality_unknown"


def test_no_lookahead_join_uses_exit_date_only() -> None:
    from stock_research.midtrend_post_exit_fundamental_attribution_v1 import join_exit_date_funnel_fields

    pool = pd.DataFrame([{"event_date": "2025-01-03", "asset_id": "A"}])
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": "A", "score_rank": 10},
            {"trade_date": "2025-01-07", "asset_id": "A", "score_rank": 1},
        ]
    )
    joined = join_exit_date_funnel_fields(pool, funnel)
    assert int(joined.iloc[0]["score_rank"]) == 10


def test_run_post_exit_attribution_writes_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_post_exit_fundamental_attribution_v1 import (
        run_midtrend_post_exit_fundamental_attribution_from_frames,
    )

    result = run_midtrend_post_exit_fundamental_attribution_from_frames(
        v1_holdings=_holdings_frame("v1"),
        v1_trades=_trades_frame(),
        v2_holdings=_holdings_frame("v2"),
        v2_trades=_trades_frame(),
        funnel=_funnel_frame(),
        prices=_price_frame(),
        output_dir=tmp_path,
        start_date="2025-01-02",
        end_date="2025-01-08",
    )

    for name in [
        "post_exit_observation_pool.csv",
        "post_exit_path_behavior.csv",
        "post_exit_path_bucket_summary.csv",
        "continued_winner_vs_failed_exit_comparison.csv",
        "bad_sell_path_attribution.csv",
        "bad_buy_fundamental_attribution.csv",
        "fundamental_data_coverage_audit.csv",
        "feature_separability_summary.csv",
        "run_params.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / name).exists(), name
    assert "observation_pool" in result


def test_cli_parser_and_dispatch_post_exit_attribution(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-post-exit-fundamental-attribution",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-post-exit-fundamental-attribution"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_post_exit_fundamental_attribution_v1.run_midtrend_post_exit_fundamental_attribution_cli",
        _fake_runner,
    )

    rc = cli.main(["midtrend-post-exit-fundamental-attribution", "--output-dir", str(tmp_path)])
    assert rc in {0, None}
    assert called["output_dir"] == str(tmp_path)
