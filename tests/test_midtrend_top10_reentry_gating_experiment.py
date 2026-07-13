from pathlib import Path

import pandas as pd
from stock_research import cli


def _base_regime() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date,
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
            }
            for date in ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
        ]
    )


def _build_top5_reentry_fixture(*, reentry_confirmed: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
    daily_ranks = {
        "2025-01-02": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"],
        "2025-01-03": ["B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "A"],
        "2025-01-06": ["B", "C", "D", "E", "F", "G", "H", "I", "J", "A", "K"],
        "2025-01-07": ["B", "C", "D", "E", "F", "G", "H", "I", "J", "A", "K"],
    }
    prices = {key: [10.0, 10.0, 10.0, 10.0] for key in list("BCDEFGHIJK")}
    prices["A"] = [10.0, 9.8, 10.8, 11.5]
    prices["B"] = [10.0, 10.1, 10.2, 10.3]
    prices["C"] = [10.0, 10.1, 10.15, 10.2]
    prices["D"] = [10.0, 10.05, 10.1, 10.15]
    prices["F"] = [10.0, 10.0, 9.95, 9.9]

    funnel_rows: list[dict[str, object]] = []
    price_rows: list[dict[str, object]] = []
    for date_idx, trade_date in enumerate(dates):
        for rank, asset_id in enumerate(daily_ranks[trade_date], start=1):
            technical_ok = reentry_confirmed or asset_id != "A" or trade_date not in {"2025-01-06", "2025-01-07"}
            score = 120.0 - rank
            if asset_id == "A" and trade_date == "2025-01-03":
                score = 100.0
            if asset_id == "A" and trade_date in {"2025-01-06", "2025-01-07"}:
                score = 111.0
            funnel_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "score_rank": rank,
                    "shadow_top10_rank": rank,
                    "rank": rank,
                    "score_total": score,
                    "mid_trend_funnel_score": score,
                    "mid_trend_layer": "stable_trend_watch",
                    "mainline_status": "sustained_mainline",
                    "industry_mainline_score_v1": 0.8,
                    "industry_name": "Tech",
                    "stock_name": asset_id,
                    "ret_20_score": 90,
                    "ret_60_score": 90,
                    "ma20_slope_score": 90,
                    "ma60_slope_score": 90,
                    "trend_r2_20_score": 90,
                    "stock_excess_ret_20_score": 90 if technical_ok else 60,
                    "sector_ret_20_score": 85,
                    "max_drawdown_20_score": 85 if technical_ok else 40,
                    "volatility_20_score": 70,
                    "atr_pct_score": 70,
                }
            )
            close = prices[asset_id][date_idx]
            price_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                }
            )
    return pd.DataFrame(funnel_rows), pd.DataFrame(price_rows)


def test_gating_variant_configs_cover_rank_score_cooldown_and_combined() -> None:
    from stock_research.midtrend_top10_reentry_gating_experiment import (
        default_reentry_gating_variant_configs,
    )

    configs = default_reentry_gating_variant_configs()
    by_name = {item.variant_name: item for item in configs}
    assert by_name["reentry_rank15"].reentry_rank_cap == 15
    assert by_name["score_improvement_strict"].require_score_improvement is True
    assert by_name["cooldown_5d"].cooldown_days == 5
    assert by_name["combined_strict"].min_max_drawdown_20_score == 70


def test_gating_experiment_writes_output_package(tmp_path: Path) -> None:
    from stock_research.midtrend_top10_reentry_gating_experiment import (
        run_midtrend_top10_reentry_gating_experiment_from_frames,
    )

    funnel, prices = _build_top5_reentry_fixture(reentry_confirmed=True)
    result = run_midtrend_top10_reentry_gating_experiment_from_frames(
        regime=_base_regime(),
        funnel=funnel,
        prices=prices,
        start_date="2025-01-02",
        end_date="2025-01-07",
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert "top10_reference" in summary["variant_name"].tolist()
    for name in [
        "top10_candidate_baseline_check.csv",
        "baseline_vs_top10_candidate.md",
        "baseline_vs_reentry_gating_variants.csv",
        "baseline_vs_reentry_gating_variants.md",
        "reentry_gating_event_log.csv",
        "reentry_gating_skip_reasons.csv",
        "reentry_gating_trade_contribution.csv",
        "reentry_left_tail_analysis.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / name).exists(), name


def test_cooldown_and_rank_cap_can_zero_out_reentry(tmp_path: Path) -> None:
    from stock_research.midtrend_top10_reentry_experiment import Top10ReentryVariantConfig
    from stock_research.midtrend_top10_reentry_gating_experiment import (
        run_midtrend_top10_reentry_gating_experiment_from_frames,
    )

    funnel, prices = _build_top5_reentry_fixture(reentry_confirmed=True)
    result = run_midtrend_top10_reentry_gating_experiment_from_frames(
        regime=_base_regime(),
        funnel=funnel,
        prices=prices,
        start_date="2025-01-02",
        end_date="2025-01-07",
        output_dir=tmp_path,
        variants=[
            Top10ReentryVariantConfig("baseline_top5", 5, 10),
            Top10ReentryVariantConfig("top10_reference", 10, 10),
            Top10ReentryVariantConfig(
                "combined_strict",
                10,
                10,
                reentry_mode="strict_top20_reentry",
                max_reentry_slots=1,
                reentry_rank_cap=12,
                require_score_improvement=True,
                require_rank_improvement=True,
                min_stock_excess_ret_20_score=85,
                min_max_drawdown_20_score=70,
                cooldown_days=5,
            ),
        ],
    )

    row = result["summary"][result["summary"]["variant_name"].eq("combined_strict")].iloc[0]
    assert row["executed_reentry_count"] == 0


def test_cli_parser_and_dispatch_gating_experiment(tmp_path: Path, monkeypatch) -> None:
    args = cli.build_parser().parse_args(
        [
            "midtrend-top10-reentry-gating-experiment",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-top10-reentry-gating-experiment"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"summary_csv": str(tmp_path / "baseline_vs_reentry_gating_variants.csv")}}

    monkeypatch.setattr(
        "stock_research.midtrend_top10_reentry_gating_experiment.run_midtrend_top10_reentry_gating_experiment_cli",
        _fake_runner,
    )

    rc = cli.main(["midtrend-top10-reentry-gating-experiment", "--output-dir", str(tmp_path)])

    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
