from pathlib import Path

import pandas as pd

from stock_research import cli
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


def test_compare_baseline_to_reference_reports_series_and_row_count_diffs(
    tmp_path: Path,
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


def test_daily_meta_lookup_reads_assets_even_when_not_in_protected_selection() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import build_daily_meta_lookup

    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "score_rank": 3,
                "mid_trend_layer": "stable_trend_watch",
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "score_rank": 25,
                "mid_trend_layer": "pullback_reacceleration_watch",
            },
        ]
    )

    lookup = build_daily_meta_lookup(funnel)

    assert ("2025-01-03", "A") in lookup
    assert lookup[("2025-01-03", "A")]["score_rank"] == 25


def test_daily_meta_lookup_marks_missing_meta_state() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import resolve_asset_day_meta

    meta = resolve_asset_day_meta({}, trade_date="2025-01-03", asset_id="A")

    assert meta["missing_meta_state"] == "missing_meta_state"
    assert pd.isna(meta["score_rank"])


def test_entry_soft_weight_reduces_weight_and_keeps_released_weight_in_cash() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import (
        MidTrendSoftOwnershipConfig,
        apply_entry_soft_weight,
    )

    config = MidTrendSoftOwnershipConfig(variant_name="entry_soft_weight_v1")
    day = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "base_target_weight": 0.2,
                "score_rank": 5,
                "mid_trend_layer": "stable_trend_watch",
                "confirmed_regime_state": "bull_trend",
                "max_drawdown_20_score": 80,
                "stock_excess_ret_20_score": 80,
            },
            {
                "asset_id": "B",
                "base_target_weight": 0.2,
                "score_rank": 35,
                "mid_trend_layer": "high_elasticity_watch",
                "confirmed_regime_state": "bull_trend",
                "max_drawdown_20_score": 70,
                "stock_excess_ret_20_score": 70,
            },
        ]
    )

    adjusted = apply_entry_soft_weight(day, config=config)

    assert adjusted.loc[adjusted["asset_id"] == "A", "adjusted_target_weight"].iloc[0] == 0.2
    assert adjusted.loc[adjusted["asset_id"] == "B", "adjusted_target_weight"].iloc[0] == 0.14
    assert adjusted["adjusted_target_weight"].sum() == 0.34
    assert adjusted["released_to_cash"].sum() == 0.06


def test_ownership_state_allows_noisy_winner_with_rank_memory_and_profit_cushion() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import (
        MidTrendSoftOwnershipConfig,
        evaluate_ownership_state,
    )

    config = MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1")
    state = evaluate_ownership_state(
        meta={
            "score_rank": 22,
            "mid_trend_layer": "pullback_reacceleration_watch",
            "max_drawdown_20_score": 60,
            "stock_excess_ret_20_score": 65,
        },
        prior_best_rank=4,
        profit_cushion=0.18,
        atr_damage=False,
        repeated_rank_break=False,
        config=config,
    )

    assert state["ownership_state"] == "owned_noisy_but_valid"
    assert state["confirmed_damage_flag"] is False


def test_ownership_state_treats_risk_exclusion_as_confirmed_damage() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import (
        MidTrendSoftOwnershipConfig,
        evaluate_ownership_state,
    )

    config = MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1")
    state = evaluate_ownership_state(
        meta={
            "score_rank": 70,
            "mid_trend_layer": "risk_exclusion_watch",
            "max_drawdown_20_score": 20,
            "stock_excess_ret_20_score": 20,
        },
        prior_best_rank=3,
        profit_cushion=-0.02,
        atr_damage=False,
        repeated_rank_break=True,
        config=config,
    )

    assert state["ownership_state"] == "ownership_broken"
    assert state["confirmed_damage_flag"] is True


def test_partial_exit_variant_reduces_weight_without_extending_holding_by_ownership() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import determine_exit_action

    result = determine_exit_action(
        variant_name="partial_exit_v1",
        baseline_exit_signal=True,
        ownership_state="owned_noisy_but_valid",
        confirmed_damage=False,
        current_weight=0.2,
        reduce_fraction=0.5,
    )

    assert result["exit_action"] == "reduce"
    assert result["exit_fraction"] == 0.5
    assert result["whether_exit_was_suppressed_by_ownership"] is False


def test_confirmed_damage_forces_full_exit_for_all_variants() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import determine_exit_action

    result = determine_exit_action(
        variant_name="ownership_hold_v1",
        baseline_exit_signal=True,
        ownership_state="owned_noisy_but_valid",
        confirmed_damage=True,
        current_weight=0.2,
        reduce_fraction=0.5,
    )

    assert result["exit_action"] == "full_exit"
    assert result["exit_fraction"] == 1.0


def test_run_soft_ownership_experiment_writes_required_artifacts(tmp_path: Path) -> None:
    from stock_research.mid_trend_soft_ownership_v1 import (
        run_mid_trend_soft_ownership_experiment,
    )

    result = run_mid_trend_soft_ownership_experiment(
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
        baseline_result={
            "equity": pd.DataFrame(
                [{"trade_date": "2025-01-02", "daily_return": 0.01, "equity": 1.01}]
            ),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy_family": "current_mid_trend_strategy_v1",
                        "total_return": 0.01,
                        "annualized_return": 0.01,
                        "max_drawdown": -0.01,
                        "days": 1,
                    }
                ]
            ),
            "holdings": pd.DataFrame(
                [{"trade_date": "2025-01-02", "asset_id": "A", "target_weight": 0.2}]
            ),
            "trades": pd.DataFrame(
                [{"trade_date": "2025-01-02", "asset_id": "A", "action": "buy"}]
            ),
        },
        baseline_reference_check={"baseline_match": True},
        funnel=pd.DataFrame(),
        regime=pd.DataFrame(),
        prices=pd.DataFrame(),
        variants=["baseline"],
    )

    assert (tmp_path / "code_audit.md").exists()
    assert (tmp_path / "baseline_vs_variants.csv").exists()
    assert (tmp_path / "baseline_vs_variants.md").exists()
    assert (tmp_path / "final_interpretation.md").exists()
    assert "paths" in result


def test_cli_parser_accepts_mid_trend_soft_ownership_command() -> None:
    args = cli.build_parser().parse_args(
        [
            "mid-trend-soft-ownership-optimize",
            "--output-dir",
            "outputs/research/test_soft_ownership",
        ]
    )
    assert args.command == "mid-trend-soft-ownership-optimize"
    assert args.start_date == "2025-01-01"
    assert args.end_date == "2026-06-12"


def test_cli_dispatch_calls_soft_ownership_runner(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {
            "paths": {
                "baseline_vs_variants_csv": str(tmp_path / "baseline_vs_variants.csv")
            }
        }

    monkeypatch.setattr(
        "stock_research.mid_trend_soft_ownership_v1.run_mid_trend_soft_ownership_cli",
        _fake_runner,
    )

    rc = cli.main(["mid-trend-soft-ownership-optimize", "--output-dir", str(tmp_path)])

    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"


def test_variant_summary_includes_exposure_metrics_and_return_per_unit_exposure() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import summarize_variant_metrics

    equity = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "daily_return": 0.01,
                "equity": 1.01,
                "invested_weight": 0.8,
            },
            {
                "trade_date": "2025-01-03",
                "daily_return": 0.00,
                "equity": 1.01,
                "invested_weight": 0.6,
            },
        ]
    )
    trades = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "action": "buy", "pnl": 0.1, "holding_days": 5},
            {"trade_date": "2025-01-03", "asset_id": "A", "action": "sell", "pnl": -0.05, "holding_days": 3},
        ]
    )
    audit = pd.DataFrame(
        [
            {"audit_label": "bad_buy"},
            {"audit_label": "bad_sell"},
        ]
    )

    summary = summarize_variant_metrics("baseline", equity=equity, trades=trades, audit_detail=audit)

    assert "average_exposure" in summary
    assert "cash_weight_avg" in summary
    assert "return_per_unit_exposure" in summary
