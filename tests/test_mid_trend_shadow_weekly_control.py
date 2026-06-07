from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_weekly_control import (
    build_mid_trend_shadow_weekly_control_review_from_frames,
    _simulate_variant,
    _target_assets_for_variant,
    _weights_for_variant,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-07", "2025-01-13", "2025-01-14"]
    industries = [
        "计算机、通信和其他电子设备制造业",
        "电气机械和器材制造业",
        "有色金属冶炼和压延加工业",
        "专用设备制造业",
        "通用设备制造业",
        "医药制造业",
    ]
    for day_index, trade_date in enumerate(dates):
        ranking = ["A", "B", "C", "D", "E", "F", "G", "H"]
        if trade_date >= "2025-01-13":
            ranking = ["F", "A", "B", "C", "D", "E", "G", "H"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ts_code": f"{rank:06d}.SZ",
                    "stock_name": f"Stock{asset_id}",
                    "industry_name": industries[(rank - 1) % len(industries)],
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.7,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank + day_index,
                    "score_rank": rank,
                    "volatility_20_score": 40,
                    "trend_r2_20_score": 90,
                    "ret_20_score": 80,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-01-31", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], start=1):
            close = 10.0 + day_index * (0.10 + asset_index * 0.01)
            if asset_id == "F" and trade_date >= pd.Timestamp("2025-01-13"):
                close = 13.0 - (day_index - 6) * 0.6
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "open": close,
                    "close": close,
                    "amount": 1000000,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)


def test_weekly_control_review_builds_variants_and_outputs(tmp_path: Path):
    result = build_mid_trend_shadow_weekly_control_review_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        output_dir=tmp_path,
        transaction_cost_bps=20.0,
    )

    summary = result["summary"]
    assert {
        "baseline_top5_weekly",
        "top5_weekly_hold_buffer_top10",
        "top5_weekly_max_2_replacements",
        "top5_weekly_ma20_exit",
        "top5_weekly_peak_drawdown_12_exit",
        "top5_weekly_market_regime_throttle",
        "top5_adaptive_hold_strong_stale_v1",
        "top5_adaptive_regime_gated_max2_v1",
        "top5_adaptive_quality_gate_v1",
    }.issubset(set(summary["variant_name"]))
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["equity_curve"]).exists()
    assert Path(result["paths"]["positions"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_hold_buffer_reduces_replacement_turnover():
    result = build_mid_trend_shadow_weekly_control_review_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        transaction_cost_bps=20.0,
    )
    summary = result["summary"].set_index("variant_name")

    assert (
        summary.loc["top5_weekly_hold_buffer_top10", "trade_rows"]
        < summary.loc["baseline_top5_weekly", "trade_rows"]
    )


def test_weekly_control_hard_exits_risk_layer_even_when_replacement_limited():
    detail = _funnel_detail()
    risk_row = detail[
        detail["trade_date"].eq("2025-01-13") & detail["asset_id"].eq("C")
    ].index[0]
    detail.loc[risk_row, "mid_trend_layer"] = "risk_exclusion_watch"
    detail.loc[risk_row, "mid_trend_funnel_score"] = 200
    detail.loc[risk_row, "trend_r2_20_score"] = 99

    result = build_mid_trend_shadow_weekly_control_review_from_frames(
        funnel_detail=detail,
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        max_weekly_replacements=0,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    variant_positions = positions[
        positions["variant_name"].eq("top5_weekly_max_2_replacements")
        & positions["rebalance_date"].eq("2025-01-13")
    ]
    assert "C" not in set(variant_positions["asset_id"])


def test_trend_holding_protection_keeps_strong_pullback_holding_not_weak_one():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": "F", "shadow_top10_rank": 1},
            {"trade_date": "2025-01-13", "asset_id": "B", "shadow_top10_rank": 2},
            {"trade_date": "2025-01-13", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2025-01-13", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2025-01-13", "asset_id": "E", "shadow_top10_rank": 5},
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": "F",
                "shadow_top10_rank": 1,
                "trend_r2_20_score": 92,
                "ret_20_score": 88,
                "industry_mainline_score_v1": 0.62,
                "max_drawdown_20_score": 75,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "A",
                "shadow_top10_rank": 6,
                "trend_r2_20_score": 91,
                "ret_20_score": 86,
                "industry_mainline_score_v1": 0.58,
                "max_drawdown_20_score": 72,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "B",
                "shadow_top10_rank": 2,
                "trend_r2_20_score": 40,
                "ret_20_score": 35,
                "industry_mainline_score_v1": 0.30,
                "max_drawdown_20_score": 45,
            },
            {"trade_date": "2025-01-13", "asset_id": "C", "shadow_top10_rank": 3},
            {"trade_date": "2025-01-13", "asset_id": "D", "shadow_top10_rank": 4},
            {"trade_date": "2025-01-13", "asset_id": "E", "shadow_top10_rank": 5},
            {
                "trade_date": "2025-01-13",
                "asset_id": "G",
                "shadow_top10_rank": 7,
                "trend_r2_20_score": 55,
                "ret_20_score": 50,
                "industry_mainline_score_v1": 0.35,
                "max_drawdown_20_score": 40,
            },
        ]
    )

    protected_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_trend_holding_protection_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert "A" in protected_assets
    assert "G" not in protected_assets
    assert protected_assets == ["A", "F", "B", "C", "D"]


def test_max2_trend_holding_protection_preserves_strong_stale_before_other_stale():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": "A",
                "shadow_top10_rank": 6,
                "trend_r2_20_score": 92,
                "ret_20_score": 85,
                "industry_mainline_score_v1": 0.62,
                "max_drawdown_20_score": 70,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "B",
                "shadow_top10_rank": 7,
                "trend_r2_20_score": 50,
                "ret_20_score": 40,
                "industry_mainline_score_v1": 0.35,
                "max_drawdown_20_score": 40,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "C",
                "shadow_top10_rank": 8,
                "trend_r2_20_score": 45,
                "ret_20_score": 35,
                "industry_mainline_score_v1": 0.30,
                "max_drawdown_20_score": 35,
            },
        ]
    )

    protected_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_trend_holding_protection_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert protected_assets == ["A", "B", "C", "F", "G"]


def test_selective_trend_holding_protection_skips_old_holding_when_new_candidate_is_much_stronger():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "industry_mainline_score_v1": mainline,
            }
            for rank, (asset_id, score, mainline) in enumerate(
                [
                    ("F", 98, 0.72),
                    ("G", 96, 0.68),
                    ("H", 94, 0.65),
                    ("I", 92, 0.62),
                    ("J", 90, 0.60),
                ],
                start=1,
            )
        ]
    )
    buffer_signals = pd.concat(
        [
            signals,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2025-01-13",
                        "asset_id": "A",
                        "shadow_top10_rank": 6,
                        "mid_trend_funnel_score": 82,
                        "trend_r2_20_score": 92,
                        "ret_20_score": 85,
                        "industry_mainline_score_v1": 0.50,
                        "max_drawdown_20_score": 70,
                    },
                    {"trade_date": "2025-01-13", "asset_id": "B", "shadow_top10_rank": 7},
                    {"trade_date": "2025-01-13", "asset_id": "C", "shadow_top10_rank": 8},
                    {"trade_date": "2025-01-13", "asset_id": "D", "shadow_top10_rank": 9},
                    {"trade_date": "2025-01-13", "asset_id": "E", "shadow_top10_rank": 10},
                ]
            ),
        ],
        ignore_index=True,
    )

    protected_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_selective_trend_holding_protection_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert protected_assets == ["C", "D", "E", "F", "G"]


def test_selective_trend_holding_protection_keeps_old_holding_when_new_candidate_edge_is_small():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "industry_mainline_score_v1": mainline,
            }
            for rank, (asset_id, score, mainline) in enumerate(
                [
                    ("F", 88, 0.58),
                    ("G", 86, 0.56),
                    ("H", 84, 0.54),
                    ("I", 82, 0.52),
                    ("J", 80, 0.50),
                ],
                start=1,
            )
        ]
    )
    buffer_signals = pd.concat(
        [
            signals,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2025-01-13",
                        "asset_id": "A",
                        "shadow_top10_rank": 6,
                        "mid_trend_funnel_score": 84,
                        "trend_r2_20_score": 92,
                        "ret_20_score": 85,
                        "industry_mainline_score_v1": 0.55,
                        "max_drawdown_20_score": 70,
                    },
                    {"trade_date": "2025-01-13", "asset_id": "B", "shadow_top10_rank": 7},
                    {"trade_date": "2025-01-13", "asset_id": "C", "shadow_top10_rank": 8},
                    {"trade_date": "2025-01-13", "asset_id": "D", "shadow_top10_rank": 9},
                    {"trade_date": "2025-01-13", "asset_id": "E", "shadow_top10_rank": 10},
                ]
            ),
        ],
        ignore_index=True,
    )

    protected_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_selective_trend_holding_protection_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert protected_assets == ["A", "C", "D", "F", "G"]


def test_quality_sorted_stale_keeps_best_current_state_not_insertion_order():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": "A",
                "shadow_top10_rank": 11,
                "mid_trend_funnel_score": 70,
                "trend_r2_20_score": 40,
                "ret_20_score": 35,
                "industry_mainline_score_v1": 0.25,
                "max_drawdown_20_score": 30,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "B",
                "shadow_top10_rank": 7,
                "mid_trend_funnel_score": 92,
                "trend_r2_20_score": 92,
                "ret_20_score": 88,
                "industry_mainline_score_v1": 0.58,
                "max_drawdown_20_score": 72,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "C",
                "shadow_top10_rank": 8,
                "mid_trend_funnel_score": 85,
                "trend_r2_20_score": 83,
                "ret_20_score": 78,
                "industry_mainline_score_v1": 0.50,
                "max_drawdown_20_score": 62,
            },
        ]
    )

    target_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_quality_sorted_stale_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert target_assets == ["B", "C", "D", "F", "G"]


def test_risk_override_can_replace_more_than_two_when_current_holdings_are_broken():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    rows = []
    for idx, asset_id in enumerate(["A", "B", "C", "D"]):
        rows.append(
            {
                "trade_date": "2025-01-13",
                "asset_id": asset_id,
                "shadow_top10_rank": 20 + idx,
                "mid_trend_funnel_score": 60 - idx,
                "trend_r2_20_score": 45,
                "ret_20_score": 50,
                "industry_mainline_score_v1": 0.28,
                "max_drawdown_20_score": 35,
            }
        )
    rows.append(
        {
            "trade_date": "2025-01-13",
            "asset_id": "E",
            "shadow_top10_rank": 6,
            "mid_trend_funnel_score": 91,
            "trend_r2_20_score": 90,
            "ret_20_score": 85,
            "industry_mainline_score_v1": 0.55,
            "max_drawdown_20_score": 70,
        }
    )
    buffer_signals = pd.DataFrame(rows)

    target_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_quality_sorted_risk_override_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert target_assets == ["E", "F", "G", "H", "I"]


def test_selective_quality_sorted_protection_uses_quality_for_unprotected_stale_fill():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": "A",
                "shadow_top10_rank": 11,
                "mid_trend_funnel_score": 70,
                "trend_r2_20_score": 40,
                "ret_20_score": 35,
                "industry_mainline_score_v1": 0.25,
                "max_drawdown_20_score": 30,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "B",
                "shadow_top10_rank": 7,
                "mid_trend_funnel_score": 92,
                "trend_r2_20_score": 92,
                "ret_20_score": 88,
                "industry_mainline_score_v1": 0.58,
                "max_drawdown_20_score": 72,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "C",
                "shadow_top10_rank": 8,
                "mid_trend_funnel_score": 85,
                "trend_r2_20_score": 83,
                "ret_20_score": 78,
                "industry_mainline_score_v1": 0.50,
                "max_drawdown_20_score": 62,
            },
        ]
    )

    target_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_selective_quality_sorted_protection_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert target_assets == ["B", "C", "D", "F", "G"]


def test_no_state_stale_repair_replaces_only_missing_state_stale():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-13",
                "asset_id": "B",
                "shadow_top10_rank": 7,
                "mid_trend_funnel_score": 92,
                "trend_r2_20_score": 92,
                "ret_20_score": 88,
                "industry_mainline_score_v1": 0.58,
                "max_drawdown_20_score": 72,
            },
            {
                "trade_date": "2025-01-13",
                "asset_id": "C",
                "shadow_top10_rank": 8,
                "mid_trend_funnel_score": 85,
                "trend_r2_20_score": 83,
                "ret_20_score": 78,
                "industry_mainline_score_v1": 0.50,
                "max_drawdown_20_score": 62,
            },
        ]
    )

    target_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-13",
        variant_name="top5_weekly_max2_no_state_stale_repair_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    assert target_assets == ["C", "B", "D", "F", "G"]


def test_drawdown_throttle_reduces_exposure_after_portfolio_drawdown():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-17", freq="B")):
        for asset_id in list("ABCDEFGHIJ"):
            close = 100.0
            if asset_id in set("ABCDE") and trade_date >= pd.Timestamp("2025-01-06"):
                close = 88.0
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": close + date_index * 0.01,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-17",
        variant_name="top5_weekly_max2_drawdown_throttle_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    second_rebalance = positions[positions["rebalance_date"].eq("2025-01-13")]
    assert round(float(second_rebalance["weight"].sum()), 6) == 0.6


def test_drawdown_throttle_matches_max2_when_not_triggered():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {"trade_date": "2025-01-13", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "A", "B"], start=1)
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-17", freq="B")):
        for asset_id in list("ABCDEFGH"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )
    price_frame = pd.DataFrame(prices)

    baseline = _simulate_variant(
        signals,
        signals,
        price_frame,
        start_date="2025-01-03",
        end_date="2025-01-17",
        variant_name="top5_weekly_max_2_replacements",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=20.0,
    )
    throttle = _simulate_variant(
        signals,
        signals,
        price_frame,
        start_date="2025-01-03",
        end_date="2025-01-17",
        variant_name="top5_weekly_max2_drawdown_throttle_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=20.0,
        drawdown_throttle_threshold=-0.99,
        drawdown_throttle_invested_weight=0.8,
        drawdown_throttle_max_replacements=1,
    )

    pd.testing.assert_series_equal(
        baseline["equity_curve"].set_index("date")["equity"],
        throttle["equity_curve"].set_index("date")["equity"],
        check_names=False,
    )
    assert int(throttle["summary"]["drawdown_throttle_trigger_count"]) == 0
    assert throttle["summary"]["trade_rows"] == baseline["summary"]["trade_rows"]


def test_rank_weighted_top5_uses_declining_position_weights():
    mild = _weights_for_variant(
        "top5_weekly_max2_rank_weight_mild_v1",
        ["A", "B", "C", "D", "E"],
        invested_weight=1.0,
    )
    aggressive = _weights_for_variant(
        "top5_weekly_max2_rank_weight_aggressive_v1",
        ["A", "B", "C", "D", "E"],
        invested_weight=1.0,
    )

    assert mild == {"A": 0.24, "B": 0.22, "C": 0.20, "D": 0.18, "E": 0.16}
    assert aggressive == {"A": 0.30, "B": 0.25, "C": 0.20, "D": 0.15, "E": 0.10}


def test_adaptive_daily_check_can_rebalance_on_non_weekly_signal_day():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "max_drawdown_20_score": 70,
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-06",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "market_regime": "mainline",
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-06",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "market_regime": "mainline",
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": 85,
                "ret_20_score": 85,
                "max_drawdown_20_score": 70,
            }
            for rank, (asset_id, score) in enumerate(
                [("F", 120), ("A", 95), ("B", 94), ("C", 93), ("D", 92), ("E", 70)],
                start=1,
            )
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-10", freq="B")):
        for asset_id in list("ABCDEF"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-10",
        variant_name="top5_adaptive_daily_check_max2_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    adaptive_trades = result["trades"]
    assert "2025-01-07" in set(adaptive_trades["trade_date"])
    positions = result["positions"]
    assert "F" in set(positions[positions["rebalance_date"].eq("2025-01-07")]["asset_id"])


def test_adaptive_daily_check_respects_weekly_replacement_budget():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "max_drawdown_20_score": 70,
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": 85,
                "ret_20_score": 85,
                "max_drawdown_20_score": 70,
            }
            for rank, (asset_id, score) in enumerate(
                [("F", 120), ("A", 95), ("B", 94), ("C", 93), ("D", 92), ("E", 70)],
                start=1,
            )
        ]
        + [
            {
                "trade_date": "2025-01-08",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": 85,
                "ret_20_score": 85,
                "max_drawdown_20_score": 70,
            }
            for rank, (asset_id, score) in enumerate(
                [("G", 130), ("F", 120), ("A", 95), ("B", 94), ("C", 93), ("D", 70), ("E", 60)],
                start=1,
            )
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-10", freq="B")):
        for asset_id in list("ABCDEFG"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-10",
        variant_name="top5_adaptive_daily_check_max2_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=1,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    assert "F" in set(positions[positions["rebalance_date"].eq("2025-01-07")]["asset_id"])
    assert "2025-01-08" not in set(positions["rebalance_date"])


def test_adaptive_hold_strong_stale_keeps_strong_holding_on_daily_rebalance():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 85,
                "ret_20_score": 80,
                "industry_mainline_score_v1": 0.60,
                "max_drawdown_20_score": 70,
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": trend,
                "ret_20_score": ret20,
                "industry_mainline_score_v1": mainline,
                "max_drawdown_20_score": drawdown,
            }
            for rank, (asset_id, score, trend, ret20, mainline, drawdown) in enumerate(
                [
                    ("F", 120, 86, 82, 0.62, 72),
                    ("G", 118, 86, 82, 0.61, 72),
                    ("B", 96, 84, 78, 0.58, 68),
                    ("C", 95, 84, 78, 0.58, 68),
                    ("D", 94, 84, 78, 0.58, 68),
                    ("A", 93, 91, 88, 0.64, 76),
                    ("E", 70, 55, 50, 0.30, 40),
                ],
                start=1,
            )
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-10", freq="B")):
        for asset_id in list("ABCDEFG"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-10",
        variant_name="top5_adaptive_hold_strong_stale_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    rebalance_assets = set(positions[positions["rebalance_date"].eq("2025-01-07")]["asset_id"])
    assert "A" in rebalance_assets
    assert "E" not in rebalance_assets


def test_adaptive_hold_strong_stale_does_not_exceed_max_replacement_budget():
    signals = pd.DataFrame(
        [
            {"trade_date": "2025-01-07", "asset_id": asset_id, "shadow_top10_rank": rank}
            for rank, asset_id in enumerate(["F", "G", "H", "I", "J"], start=1)
        ]
    )
    buffer_signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "trend_r2_20_score": trend,
                "ret_20_score": ret20,
                "industry_mainline_score_v1": mainline,
                "max_drawdown_20_score": drawdown,
            }
            for rank, (asset_id, trend, ret20, mainline, drawdown) in enumerate(
                [
                    ("A", 92, 88, 0.64, 76),
                    ("B", 91, 87, 0.63, 74),
                    ("C", 45, 40, 0.30, 35),
                    ("D", 44, 39, 0.30, 34),
                    ("E", 43, 38, 0.30, 33),
                    ("F", 86, 82, 0.62, 72),
                    ("G", 85, 81, 0.61, 71),
                    ("H", 84, 80, 0.60, 70),
                    ("I", 83, 79, 0.59, 69),
                    ("J", 82, 78, 0.58, 68),
                ],
                start=1,
            )
        ]
    )

    target_assets, _ = _target_assets_for_variant(
        signals,
        buffer_signals=buffer_signals,
        trade_date="2025-01-07",
        variant_name="top5_adaptive_hold_strong_stale_v1",
        current_assets=["A", "B", "C", "D", "E"],
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
    )

    sold_assets = set(["A", "B", "C", "D", "E"]) - set(target_assets)
    assert len(sold_assets) <= 2
    assert {"A", "B"}.issubset(set(target_assets))


def test_adaptive_regime_gated_skips_non_weekly_rebalance_in_rotation_regime():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "market_regime": "mainline",
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-06",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "market_regime": "mainline",
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": 85,
                "ret_20_score": 85,
                "market_regime": "rotation",
            }
            for rank, (asset_id, score) in enumerate(
                [("F", 125), ("A", 95), ("B", 94), ("C", 93), ("D", 92), ("E", 70)],
                start=1,
            )
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-10", freq="B")):
        for asset_id in list("ABCDEF"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-10",
        variant_name="top5_adaptive_regime_gated_max2_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    assert "2025-01-07" not in set(positions["rebalance_date"])


def test_adaptive_quality_gate_blocks_low_quality_new_buy_on_daily_rebalance():
    signals = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": 100 - rank,
                "trend_r2_20_score": 80,
                "ret_20_score": 80,
                "industry_mainline_score_v1": 0.60,
                "max_drawdown_20_score": 70,
                "volatility_20_score": 40,
            }
            for rank, asset_id in enumerate(["A", "B", "C", "D", "E"], start=1)
        ]
        + [
            {
                "trade_date": "2025-01-07",
                "asset_id": asset_id,
                "shadow_top10_rank": rank,
                "mid_trend_funnel_score": score,
                "trend_r2_20_score": trend,
                "ret_20_score": ret20,
                "industry_mainline_score_v1": mainline,
                "max_drawdown_20_score": drawdown,
                "volatility_20_score": volatility,
            }
            for rank, (asset_id, score, trend, ret20, mainline, drawdown, volatility) in enumerate(
                [
                    ("F", 125, 88, 86, 0.20, 35, 98),
                    ("A", 95, 82, 78, 0.58, 68, 45),
                    ("B", 94, 82, 78, 0.58, 68, 45),
                    ("C", 93, 82, 78, 0.58, 68, 45),
                    ("D", 92, 82, 78, 0.58, 68, 45),
                    ("E", 70, 60, 55, 0.40, 45, 70),
                ],
                start=1,
            )
        ]
    )
    prices = []
    for date_index, trade_date in enumerate(pd.date_range("2025-01-03", "2025-01-10", freq="B")):
        for asset_id in list("ABCDEF"):
            prices.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "close": 100.0 + date_index * 0.1,
                }
            )

    result = _simulate_variant(
        signals,
        signals,
        pd.DataFrame(prices),
        start_date="2025-01-03",
        end_date="2025-01-10",
        variant_name="top5_adaptive_quality_gate_v1",
        top_n=5,
        buffer_rank=10,
        max_weekly_replacements=2,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=0,
    )

    positions = result["positions"]
    rebalance_dates = set(positions["rebalance_date"])
    if "2025-01-07" in rebalance_dates:
        rebalance_assets = set(positions[positions["rebalance_date"].eq("2025-01-07")]["asset_id"])
        assert "F" not in rebalance_assets
    else:
        assert "F" not in set(positions["asset_id"])


def test_cli_dispatches_weekly_control_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"variant_name": "baseline_top5_weekly"}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "equity_curve": str(tmp_path / "equity.csv"),
                "positions": str(tmp_path / "positions.csv"),
                "trades": str(tmp_path / "trades.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_weekly_control_review", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-shadow-weekly-control",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["transaction_cost_bps"] == 20.0
    assert captured["top_n"] == 5
    out = capsys.readouterr().out
    assert "mid_trend_shadow_weekly_control|summary|" in out
