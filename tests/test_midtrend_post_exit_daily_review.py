from pathlib import Path

import pandas as pd
from stock_research import cli


def test_review_priority_and_expiry_assignment() -> None:
    from stock_research.midtrend_post_exit_daily_review import assign_review_priority

    high = assign_review_priority(
        pd.Series(
            {
                "days_since_exit": 5,
                "was_held": True,
                "previous_best_rank": 8,
                "current_rank": 12,
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "hard_damage_flag": False,
                "current_mid_trend_layer": "stable_trend_watch",
            }
        )
    )
    expired = assign_review_priority(
        pd.Series(
            {
                "days_since_exit": 61,
                "was_held": True,
                "previous_best_rank": 5,
                "current_rank": 9,
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "hard_damage_flag": False,
                "current_mid_trend_layer": "stable_trend_watch",
            }
        )
    )
    assert high["review_priority"] == "HIGH"
    assert expired["review_priority"] == "EXPIRED"


def test_build_daily_review_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_post_exit_daily_review import (
        build_midtrend_post_exit_daily_review_from_frames,
    )

    observation = pd.DataFrame(
        [
            {
                "strategy_name": "v2",
                "source_variant": "top10_candidate",
                "event_date": "2025-01-02",
                "asset_id": "A",
                "stock_name_x": "A",
                "industry_name_x": "Tech",
                "event_type": "ranking_churn_sell",
                "was_held": True,
                "holding_days_before_exit": 4,
                "previous_best_rank_5_10_20": 8,
                "rank_on_exit_date": 12,
                "mid_trend_funnel_score_on_exit": 101,
                "mid_trend_layer_on_exit": "stable_trend_watch",
                "target_weight_before_exit": 0.1,
                "weight_change": -0.1,
                "sell_or_drop_reason": "sell",
                "protection_reason": "",
                "confirmed_regime_state": "bull_trend",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "fundamental_quality_bucket": "quality_unknown",
                "fundamental_momentum_bucket": "unknown",
            }
        ]
    )
    funnel = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-07",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "candidate_rank": 10,
                "mid_trend_funnel_score": 110,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "industry_mainline_score_v1": 0.8,
                "stock_excess_ret_20_score": 88,
                "max_drawdown_20_score": 80,
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
            }
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.2, "low": 9.8, "close": 10.0},
            {"trade_date": "2025-01-07", "asset_id": "A", "high": 12.2, "low": 11.8, "close": 12.0},
        ]
    )
    pit = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-07",
                "asset_id": "A",
                "fundamental_quality_bucket": "quality_unknown",
                "fundamental_momentum_bucket": "unknown",
                "pit_valid_flag": False,
            }
        ]
    )
    result = build_midtrend_post_exit_daily_review_from_frames(
        trade_date="2025-01-07",
        observation_pool=observation,
        funnel=funnel,
        prices=prices,
        pit_features=pit,
        output_dir=tmp_path,
    )
    assert (tmp_path / "midtrend_post_exit_watch_daily.csv").exists()
    assert (tmp_path / "midtrend_post_exit_watch_summary.md").exists()
    assert result["watch_daily"].iloc[0]["review_priority"] == "HIGH"


def test_cli_parser_and_dispatch_daily_review(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-post-exit-daily-review",
            "--trade-date",
            "2026-06-12",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-post-exit-daily-review"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_post_exit_daily_review.run_midtrend_post_exit_daily_review_cli",
        _fake_runner,
    )

    rc = cli.main(
        [
            "midtrend-post-exit-daily-review",
            "--trade-date",
            "2026-06-12",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in {0, None}
    assert called["trade_date"] == "2026-06-12"
