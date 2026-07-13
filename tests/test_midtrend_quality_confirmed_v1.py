from pathlib import Path

import pandas as pd
from stock_research import cli


def test_rank_quality_confirmed_candidates_excludes_quality_weak_and_applies_bonuses() -> None:
    from stock_research.midtrend_quality_confirmed_v1 import (
        MidTrendQualityVariantConfig,
        rank_quality_confirmed_candidates,
    )

    frame = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "mid_trend_funnel_score": 90.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_confirmed": True,
                "fundamental_quality_bucket": "quality_strong",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "mid_trend_funnel_score": 91.0,
                "mid_trend_layer": "high_elasticity_watch",
                "mainline_confirmed": False,
                "fundamental_quality_bucket": "quality_unknown",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "C",
                "mid_trend_funnel_score": 120.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_confirmed": True,
                "fundamental_quality_bucket": "quality_weak",
            },
        ]
    )

    ranked = rank_quality_confirmed_candidates(
        frame,
        config=MidTrendQualityVariantConfig(variant_name="v2_b_top8_quality"),
    )

    assert "C" not in ranked["asset_id"].tolist()
    assert ranked.iloc[0]["asset_id"] == "A"
    assert ranked.iloc[1]["asset_id"] == "B"


def test_build_midtrend_confirmation_trade_audit_marks_bad_sell_as_rank_churn_when_not_hard_damage() -> None:
    from stock_research.midtrend_quality_confirmed_v1 import (
        build_midtrend_confirmation_trade_audit,
    )

    trades = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "action": "sell",
                "forward_return": 0.30,
                "audit_label": "bad_sell",
            }
        ]
    )
    detail = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "score_rank": 18,
                "mid_trend_layer": "stable_trend_watch",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "fundamental_quality_bucket": "quality_unknown",
                "fundamental_confirmed": False,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "fundamental_risk_flag": False,
            }
        ]
    )

    audit = build_midtrend_confirmation_trade_audit(
        trade_audit=trades,
        funnel_detail=detail,
    )

    row = audit.iloc[0]
    assert row["combined_confirmation_state"] == "T1_M1_UNKNOWN_F"
    assert row["exit_damage_type"] == "ranking_churn_exit"


def test_run_quality_confirmed_experiment_writes_output_package(tmp_path: Path) -> None:
    from stock_research.midtrend_quality_confirmed_v1 import (
        run_midtrend_quality_confirmed_experiment_from_frames,
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
        ]
    )
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "score_rank": 1,
                "rank": 1,
                "score_total": 90.0,
                "mid_trend_funnel_score": 90.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "ret_20_score": 90,
                "ret_60_score": 90,
                "ma20_slope_score": 90,
                "ma60_slope_score": 90,
                "trend_r2_20_score": 90,
                "stock_excess_ret_20_score": 90,
                "sector_ret_20_score": 90,
                "max_drawdown_20_score": 90,
                "volatility_20_score": 80,
                "atr_pct_score": 80,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "score_rank": 1,
                "rank": 1,
                "score_total": 90.0,
                "mid_trend_funnel_score": 90.0,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "ret_20_score": 90,
                "ret_60_score": 90,
                "ma20_slope_score": 90,
                "ma60_slope_score": 90,
                "trend_r2_20_score": 90,
                "stock_excess_ret_20_score": 90,
                "sector_ret_20_score": 90,
                "max_drawdown_20_score": 90,
                "volatility_20_score": 80,
                "atr_pct_score": 80,
            },
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 11.5, "low": 10.5, "close": 11.0},
        ]
    )

    result = run_midtrend_quality_confirmed_experiment_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date="2025-01-02",
        end_date="2025-01-03",
        output_dir=tmp_path,
    )

    assert (tmp_path / "baseline_vs_quality_variants.csv").exists()
    assert (tmp_path / "midtrend_confirmation_audit_report.md").exists()
    assert (tmp_path / "final_interpretation.md").exists()
    assert "summary" in result


def test_cli_parser_and_dispatch_quality_confirmed_experiment(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-quality-confirmed-experiment",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-quality-confirmed-experiment"
    assert args.start_date == "2025-01-01"
    assert args.end_date == "2026-06-12"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"summary_csv": str(tmp_path / "baseline_vs_quality_variants.csv")}}

    monkeypatch.setattr(
        "stock_research.midtrend_quality_confirmed_v1.run_midtrend_quality_confirmed_experiment_cli",
        _fake_runner,
    )

    rc = cli.main(["midtrend-quality-confirmed-experiment", "--output-dir", str(tmp_path)])

    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
