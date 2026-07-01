from pathlib import Path

import pandas as pd
from stock_research import cli


def test_default_topn_pool_variant_configs_include_baseline_and_top8_reference() -> None:
    from stock_research.midtrend_topn_pool_reentry_sweep import (
        default_topn_pool_variant_configs,
    )

    configs = default_topn_pool_variant_configs()
    by_name = {item.variant_name: item for item in configs}

    assert by_name["baseline_top5_pool10"].final_top_n == 5
    assert by_name["baseline_top5_pool10"].candidate_pool_size == 10
    assert by_name["v2_a_top8_only_pool30"].final_top_n == 8
    assert by_name["v2_a_top8_only_pool30"].candidate_pool_size == 30


def test_run_midtrend_topn_pool_reentry_sweep_writes_output_package(tmp_path: Path) -> None:
    from stock_research.midtrend_topn_pool_reentry_sweep import (
        run_midtrend_topn_pool_reentry_sweep_from_frames,
    )

    regime = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
            },
            {
                "trade_date": "2025-01-03",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
            },
            {
                "trade_date": "2025-01-06",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
            },
        ]
    )
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "score_rank": 1,
                "shadow_top10_rank": 1,
                "rank": 1,
                "score_total": 95.0,
                "mid_trend_funnel_score": 95.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "industry_name": "Tech",
                "ret_20_score": 90,
                "ret_60_score": 90,
                "ma20_slope_score": 90,
                "ma60_slope_score": 90,
                "trend_r2_20_score": 90,
                "stock_excess_ret_20_score": 90,
                "sector_ret_20_score": 90,
                "max_drawdown_20_score": 90,
                "volatility_20_score": 70,
                "atr_pct_score": 70,
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "score_rank": 2,
                "shadow_top10_rank": 2,
                "rank": 2,
                "score_total": 90.0,
                "mid_trend_funnel_score": 90.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.7,
                "industry_name": "Tech",
                "ret_20_score": 85,
                "ret_60_score": 85,
                "ma20_slope_score": 85,
                "ma60_slope_score": 85,
                "trend_r2_20_score": 85,
                "stock_excess_ret_20_score": 85,
                "sector_ret_20_score": 85,
                "max_drawdown_20_score": 80,
                "volatility_20_score": 65,
                "atr_pct_score": 65,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "score_rank": 7,
                "shadow_top10_rank": 7,
                "rank": 7,
                "score_total": 88.0,
                "mid_trend_funnel_score": 88.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "industry_name": "Tech",
                "ret_20_score": 90,
                "ret_60_score": 90,
                "ma20_slope_score": 90,
                "ma60_slope_score": 90,
                "trend_r2_20_score": 90,
                "stock_excess_ret_20_score": 90,
                "sector_ret_20_score": 90,
                "max_drawdown_20_score": 90,
                "volatility_20_score": 70,
                "atr_pct_score": 70,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "score_rank": 1,
                "shadow_top10_rank": 1,
                "rank": 1,
                "score_total": 96.0,
                "mid_trend_funnel_score": 96.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.7,
                "industry_name": "Tech",
                "ret_20_score": 86,
                "ret_60_score": 86,
                "ma20_slope_score": 86,
                "ma60_slope_score": 86,
                "trend_r2_20_score": 86,
                "stock_excess_ret_20_score": 86,
                "sector_ret_20_score": 86,
                "max_drawdown_20_score": 82,
                "volatility_20_score": 66,
                "atr_pct_score": 66,
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "A",
                "score_rank": 2,
                "shadow_top10_rank": 2,
                "rank": 2,
                "score_total": 98.0,
                "mid_trend_funnel_score": 98.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "industry_name": "Tech",
                "ret_20_score": 92,
                "ret_60_score": 92,
                "ma20_slope_score": 92,
                "ma60_slope_score": 92,
                "trend_r2_20_score": 92,
                "stock_excess_ret_20_score": 92,
                "sector_ret_20_score": 92,
                "max_drawdown_20_score": 92,
                "volatility_20_score": 72,
                "atr_pct_score": 72,
            },
            {
                "trade_date": "2025-01-06",
                "asset_id": "B",
                "score_rank": 8,
                "shadow_top10_rank": 8,
                "rank": 8,
                "score_total": 80.0,
                "mid_trend_funnel_score": 80.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.7,
                "industry_name": "Tech",
                "ret_20_score": 80,
                "ret_60_score": 80,
                "ma20_slope_score": 80,
                "ma60_slope_score": 80,
                "trend_r2_20_score": 80,
                "stock_excess_ret_20_score": 80,
                "sector_ret_20_score": 80,
                "max_drawdown_20_score": 78,
                "volatility_20_score": 60,
                "atr_pct_score": 60,
            },
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.4, "low": 9.8, "close": 10.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 10.6, "low": 10.0, "close": 10.5},
            {"trade_date": "2025-01-06", "asset_id": "A", "high": 11.1, "low": 10.4, "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 20.5, "low": 19.5, "close": 20.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "high": 21.4, "low": 20.5, "close": 21.0},
            {"trade_date": "2025-01-06", "asset_id": "B", "high": 20.6, "low": 19.8, "close": 20.2},
        ]
    )

    result = run_midtrend_topn_pool_reentry_sweep_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date="2025-01-02",
        end_date="2025-01-06",
        output_dir=tmp_path,
    )

    required = [
        "baseline_vs_topn_pool_variants.csv",
        "baseline_vs_topn_pool_variants.md",
        "topn_pool_heatmap.csv",
        "slot_contribution_by_variant.csv",
        "marginal_slot_summary.csv",
        "ranking_churn_by_variant.csv",
        "bad_buy_bad_sell_by_topn_pool.csv",
        "exposure_concentration_by_variant.csv",
        "post_exit_watch_pool.csv",
        "post_exit_watch_summary.csv",
        "reentry_trigger_diagnostics.csv",
        "narrow_ranking_churn_carry_candidates.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name
    assert "summary" in result


def test_cli_parser_and_dispatch_midtrend_topn_pool_reentry_sweep(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-topn-pool-reentry-sweep",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-topn-pool-reentry-sweep"
    assert args.start_date == "2025-01-01"
    assert args.end_date == "2026-06-12"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"summary_csv": str(tmp_path / "baseline_vs_topn_pool_variants.csv")}}

    monkeypatch.setattr(
        "stock_research.midtrend_topn_pool_reentry_sweep.run_midtrend_topn_pool_reentry_sweep_cli",
        _fake_runner,
    )

    rc = cli.main(["midtrend-topn-pool-reentry-sweep", "--output-dir", str(tmp_path)])

    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
