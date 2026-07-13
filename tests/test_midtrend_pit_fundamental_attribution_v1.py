from pathlib import Path

import pandas as pd
from stock_research import cli


def _pit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "report_disclosure_date": "2025-01-02",
                "data_available_asof_date": "2025-01-02",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_strong",
                "fundamental_momentum_bucket": "improving",
                "fundamental_risk_flag": False,
                "revenue_growth_yoy": 0.30,
                "profit_growth_yoy": 0.25,
                "roe": 0.18,
                "operating_cashflow_to_profit": 1.1,
                "debt_ratio": 0.3,
                "market_cap": 100.0,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "report_disclosure_date": "2025-01-02",
                "data_available_asof_date": "2025-01-02",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_weak",
                "fundamental_momentum_bucket": "deteriorating",
                "fundamental_risk_flag": True,
                "revenue_growth_yoy": -0.10,
                "profit_growth_yoy": -0.20,
                "roe": 0.03,
                "operating_cashflow_to_profit": 0.2,
                "debt_ratio": 0.85,
                "market_cap": 50.0,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "C",
                "report_disclosure_date": pd.NA,
                "data_available_asof_date": pd.NA,
                "pit_valid_flag": False,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_unknown",
                "fundamental_momentum_bucket": "unknown",
                "fundamental_risk_flag": pd.NA,
                "revenue_growth_yoy": pd.NA,
                "profit_growth_yoy": pd.NA,
                "roe": pd.NA,
                "operating_cashflow_to_profit": pd.NA,
                "debt_ratio": pd.NA,
                "market_cap": 20.0,
            },
        ]
    )


def _observation_pool() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_date": "2025-01-03",
                "asset_id": "A",
                "path_class": "immediate_continuation",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "rank_on_exit_date": 8,
                "mid_trend_layer_on_exit": "stable_trend_watch",
                "industry_name": "Tech",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.9,
                "stock_excess_ret_20_score": 88,
                "max_drawdown_20_score": 80,
                "forward_return_20d": 0.12,
                "forward_return_30d": 0.16,
                "forward_return_60d": 0.24,
                "max_drawdown_after_exit_60d": -0.04,
            },
            {
                "event_date": "2025-01-03",
                "asset_id": "B",
                "path_class": "true_exit",
                "technical_confirmed": False,
                "mainline_confirmed": False,
                "midtrend_confirmation_state": "T0_M0_UNKNOWN_F",
                "rank_on_exit_date": 35,
                "mid_trend_layer_on_exit": "high_elasticity_watch",
                "industry_name": "Tech",
                "mainline_status": "neutral",
                "industry_mainline_score_v1": 0.3,
                "stock_excess_ret_20_score": 55,
                "max_drawdown_20_score": 42,
                "forward_return_20d": -0.08,
                "forward_return_30d": -0.12,
                "forward_return_60d": -0.15,
                "max_drawdown_after_exit_60d": -0.22,
            },
            {
                "event_date": "2025-01-03",
                "asset_id": "C",
                "path_class": "failed_rebound",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "rank_on_exit_date": 15,
                "mid_trend_layer_on_exit": "pullback_reacceleration_watch",
                "industry_name": "Tech",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "stock_excess_ret_20_score": 74,
                "max_drawdown_20_score": 58,
                "forward_return_20d": 0.03,
                "forward_return_30d": -0.01,
                "forward_return_60d": 0.01,
                "max_drawdown_after_exit_60d": -0.12,
            },
        ]
    )


def _trade_diag() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "audit_label": "bad_sell",
                "action": "sell",
                "forward_return": 0.20,
                "ranking_churn_flag": True,
                "hard_damage_flag": False,
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "mid_trend_layer": "stable_trend_watch",
                "score_rank": 8,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "audit_label": "bad_buy",
                "action": "buy",
                "forward_return": -0.18,
                "ranking_churn_flag": False,
                "hard_damage_flag": False,
                "technical_confirmed": False,
                "mainline_confirmed": False,
                "midtrend_confirmation_state": "T0_M0_UNKNOWN_F",
                "mid_trend_layer": "high_elasticity_watch",
                "score_rank": 20,
            },
        ]
    )


def _reentry_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    events = pd.DataFrame(
        [
            {
                "variant_name": "top10_strict_top20_reentry_slot1",
                "watch_start_date": "2025-01-03",
                "reentry_date": "2025-01-03",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "reentry_mode": "strict_top20_reentry",
                "action_taken": "executed_reentry_signal",
                "skip_reason": "",
            }
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "variant_name": "top10_strict_top20_reentry_slot1",
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "target_weight": 0.1,
                "return_after_reentry": -0.12,
                "contribution_after_reentry": -0.012,
                "forward_return_after_reentry_5d": -0.08,
                "forward_return_after_reentry_10d": -0.10,
                "forward_return_after_reentry_20d": -0.12,
                "failed_reentry_loss": -0.12,
            }
        ]
    )
    return events, trades


def test_validate_pit_input_flags_no_lookahead() -> None:
    from stock_research.midtrend_pit_fundamental_attribution_v1 import validate_pit_fundamental_input

    validation = validate_pit_fundamental_input(_pit_frame())
    assert int(validation["lookahead_violations"].sum()) == 0
    assert int(validation["usable_rows"].sum()) == 2


def test_join_observation_pool_to_pit_keeps_unknown_as_unknown() -> None:
    from stock_research.midtrend_pit_fundamental_attribution_v1 import join_observation_pool_with_pit

    joined = join_observation_pool_with_pit(_observation_pool(), _pit_frame())
    row = joined[joined["asset_id"].eq("C")].iloc[0]
    assert row["fundamental_quality_bucket"] == "quality_unknown"


def test_run_pit_attribution_writes_required_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_pit_fundamental_attribution_v1 import (
        run_midtrend_pit_fundamental_attribution_from_frames,
    )

    re_events, re_trades = _reentry_frames()
    result = run_midtrend_pit_fundamental_attribution_from_frames(
        pit_features=_pit_frame(),
        observation_pool=_observation_pool(),
        trade_diagnostics=_trade_diag(),
        reentry_event_log=re_events,
        reentry_trade_contribution=re_trades,
        output_dir=tmp_path,
    )

    for name in [
        "pit_fundamental_input_validation.csv",
        "pit_fundamental_coverage_summary.csv",
        "post_exit_observation_pool_with_pit_fundamentals.csv",
        "continued_winner_vs_failed_exit_pit_comparison.csv",
        "bad_sell_fundamental_attribution_pit.csv",
        "bad_buy_fundamental_attribution_pit.csv",
        "reentry_left_tail_fundamental_attribution_pit.csv",
        "fundamental_bucket_separability_summary.csv",
        "fundamental_rule_candidates_research_only.md",
        "run_params.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / name).exists(), name
    assert "joined_pool" in result


def test_cli_parser_and_dispatch_pit_attribution(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-pit-fundamental-attribution",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-pit-fundamental-attribution"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_pit_fundamental_attribution_v1.run_midtrend_pit_fundamental_attribution_cli",
        _fake_runner,
    )

    rc = cli.main(["midtrend-pit-fundamental-attribution", "--output-dir", str(tmp_path)])
    assert rc in {0, None}
    assert called["output_dir"] == str(tmp_path)
