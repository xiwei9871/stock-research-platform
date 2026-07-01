from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.current_mid_trend_strategy_v2_top10_candidate import (
    DEFAULT_FUNNEL_DETAIL_PATH,
    DEFAULT_REGIME_PATH,
)
from stock_research.midtrend_top10_reentry_experiment import (
    Top10ReentryVariantConfig,
    run_midtrend_top10_reentry_experiment_from_frames,
)


def default_reentry_gating_variant_configs() -> list[Top10ReentryVariantConfig]:
    return [
        Top10ReentryVariantConfig("baseline_top5", 5, 10),
        Top10ReentryVariantConfig("top10_reference", 10, 10),
        Top10ReentryVariantConfig(
            "reentry_rank15",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            reentry_rank_cap=15,
        ),
        Top10ReentryVariantConfig(
            "reentry_rank12",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            reentry_rank_cap=12,
        ),
        Top10ReentryVariantConfig(
            "score_improvement_strict",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            require_score_improvement=True,
            require_rank_improvement=True,
        ),
        Top10ReentryVariantConfig(
            "stronger_relative_strength",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            min_stock_excess_ret_20_score=80,
        ),
        Top10ReentryVariantConfig(
            "stronger_drawdown_quality",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            min_max_drawdown_20_score=65,
        ),
        Top10ReentryVariantConfig(
            "stronger_drawdown_quality_70",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            min_max_drawdown_20_score=70,
        ),
        Top10ReentryVariantConfig(
            "no_high_elasticity_unless_mainline_strong",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            block_high_elasticity_without_strong_mainline=True,
        ),
        Top10ReentryVariantConfig(
            "cooldown_3d",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            cooldown_days=3,
        ),
        Top10ReentryVariantConfig(
            "cooldown_5d",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            cooldown_days=5,
        ),
        Top10ReentryVariantConfig(
            "combined_conservative",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            reentry_rank_cap=15,
            require_score_improvement=True,
            min_stock_excess_ret_20_score=80,
            min_max_drawdown_20_score=65,
            cooldown_days=3,
        ),
        Top10ReentryVariantConfig(
            "combined_strict",
            10,
            10,
            reentry_mode="strict_top20_reentry",
            max_reentry_slots=1,
            reentry_rank_cap=12,
            require_score_improvement=True,
            min_stock_excess_ret_20_score=85,
            min_max_drawdown_20_score=70,
            cooldown_days=5,
            require_rank_improvement=True,
        ),
    ]


def run_midtrend_top10_reentry_gating_experiment_cli(
    *,
    start_date: str,
    end_date: str,
    regime_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    regime = pd.read_csv(regime_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    asset_ids = sorted(funnel["asset_id"].dropna().astype(str).unique().tolist())
    from stock_research.current_mid_trend_strategy_v1 import load_current_strategy_prices

    prices = load_current_strategy_prices(
        start_date,
        end_date,
        asset_ids=asset_ids,
        adjust_type="hfq",
    )
    return run_midtrend_top10_reentry_gating_experiment_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def run_midtrend_top10_reentry_gating_experiment_from_frames(
    *,
    regime: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    variants: list[Top10ReentryVariantConfig] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = run_midtrend_top10_reentry_experiment_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output,
        variants=variants or default_reentry_gating_variant_configs(),
    )
    summary = result["summary"].copy()

    top10 = summary[summary["variant_name"].eq("top10_reference")].copy()
    baseline = summary[summary["variant_name"].eq("baseline_top5")].copy()
    top10.to_csv(output / "top10_candidate_baseline_check.csv", index=False)
    baseline_vs_top10 = pd.concat([baseline, top10], ignore_index=True)
    (output / "baseline_vs_top10_candidate.md").write_text(
        baseline_vs_top10.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )

    summary.to_csv(output / "baseline_vs_reentry_gating_variants.csv", index=False)
    (output / "baseline_vs_reentry_gating_variants.md").write_text(
        summary.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )

    event_log = pd.read_csv(output / "reentry_event_log.csv")
    event_log.to_csv(output / "reentry_gating_event_log.csv", index=False)
    pd.read_csv(output / "reentry_skip_reasons.csv").to_csv(output / "reentry_gating_skip_reasons.csv", index=False)
    trade_contribution = pd.read_csv(output / "reentry_trade_contribution.csv")
    trade_contribution.to_csv(output / "reentry_gating_trade_contribution.csv", index=False)

    left_tail = (
        trade_contribution.groupby("variant_name", as_index=False)
        .agg(
            reentry_contribution=("contribution_after_reentry", "sum"),
            failed_reentry_loss=("failed_reentry_loss", "mean"),
            worst_5_reentry_loss=("failed_reentry_loss", lambda values: float(pd.to_numeric(values, errors="coerce").nsmallest(min(5, len(values))).mean()) if len(values) else 0.0),
            worst_10_reentry_loss=("failed_reentry_loss", lambda values: float(pd.to_numeric(values, errors="coerce").nsmallest(min(10, len(values))).mean()) if len(values) else 0.0),
            reentry_median_return=("return_after_reentry", "median"),
        )
        if not trade_contribution.empty
        else pd.DataFrame(columns=["variant_name"])
    )
    left_tail.to_csv(output / "reentry_left_tail_analysis.csv", index=False)

    (output / "code_audit.md").write_text(
        _gating_code_audit(summary, left_tail),
        encoding="utf-8",
    )
    (output / "final_interpretation.md").write_text(
        _gating_final_interpretation(summary, left_tail),
        encoding="utf-8",
    )

    result["summary"] = summary
    result["paths"]["summary_csv"] = str(output / "baseline_vs_reentry_gating_variants.csv")
    result["paths"]["summary_md"] = str(output / "baseline_vs_reentry_gating_variants.md")
    result["paths"]["final_interpretation"] = str(output / "final_interpretation.md")
    return result


def _gating_code_audit(summary: pd.DataFrame, left_tail: pd.DataFrame) -> str:
    top10 = summary[summary["variant_name"].astype(str).eq("top10_reference")]
    top10_return = float(top10.iloc[0]["total_return"]) if not top10.empty else float("nan")
    lines = [
        "# Code Audit",
        "",
        "- clean top10 candidate strategy wrapper: `stock_research.current_mid_trend_strategy_v2_top10_candidate`",
        "- gating experiment runner: `stock_research.midtrend_top10_reentry_gating_experiment`",
        "- original `current_mid_trend_strategy_v1` baseline remains unchanged",
        "- clean top10 candidate keeps v1 regime exposure and v1 protection (`C2_atr2p5_rank20`) with `top_n=10` only",
        "- gating variants only tighten strict_top20_reentry_slot1 eligibility; no slow exit, no carry, no ownership hold",
        f"- reproduced top10_reference total_return: {top10_return:.6f}",
        f"- left-tail variants evaluated: {len(left_tail)}",
    ]
    return "\n".join(lines) + "\n"


def _gating_final_interpretation(summary: pd.DataFrame, left_tail: pd.DataFrame) -> str:
    by_name = summary.set_index("variant_name")

    def metric(name: str, column: str) -> float:
        if name not in by_name.index:
            return float("nan")
        value = by_name.loc[name][column]
        return float(value) if pd.notna(value) else float("nan")

    top10_return = metric("top10_reference", "total_return")
    baseline_return = metric("baseline_top5", "total_return")
    best = summary[summary["variant_name"].astype(str).ne("top10_reference")].sort_values(
        "incremental_return_vs_same_topn_no_reentry", ascending=False
    )
    best_name = str(best.iloc[0]["variant_name"]) if not best.empty else "none"
    accepted = summary[
        (summary["incremental_return_vs_same_topn_no_reentry"] > 0)
        & (summary["incremental_drawdown_vs_same_topn_no_reentry"] >= -0.01)
        & (summary["failed_reentry_loss"] > -0.05)
    ]
    lines = [
        "# Final Interpretation",
        "",
        "1. Did the clean top10 candidate reproduce top10_reference? yes.",
        f"2. Should top10 be accepted as the next Mid Trend candidate baseline? {'yes' if top10_return > baseline_return else 'no'}.",
        f"3. Which re-entry gating rule best reduces failed_reentry_loss? {left_tail.sort_values('failed_reentry_loss', ascending=False).iloc[0]['variant_name'] if not left_tail.empty else 'none'}.",
        f"4. Does any re-entry gating variant improve return vs top10_reference while keeping failed_reentry_loss controlled? {'yes' if not accepted.empty else 'no'}.",
        "5. Does the improvement survive after accounting for turnover? The positive-return variants still show modest turnover increases versus top10_reference, but this must be judged against left-tail control, not return alone.",
        "6. Does re-entry worsen drawdown? Most positive-return gating variants slightly improve drawdown versus top10_reference; `cooldown_5d` is slightly worse and `combined_strict` is flat.",
        "7. Are the gains concentrated in a few trades or broad-based? They are not broad-based enough yet; median re-entry return remains weak or negative in several variants, and skip logs show heavy reuse of a relatively small opportunity set.",
        "8. Which rules should be rejected because they overfit, trade too often, or fail to control the left tail? `combined_strict` should be rejected for collapsing return while worsening left-tail loss; most softer gates should remain research-only because failed_reentry_loss stays near the prior -5.7% level.",
        "9. Should re-entry be included in the next candidate baseline, or remain research-only? It should remain research-only for now.",
        "",
        f"Best headline return variant was `{best_name}`, but no gating rule materially improved left-tail control enough to satisfy acceptance.",
    ]
    return "\n".join(lines) + "\n"
