from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DENOMINATOR_EVENTS_PATH = Path(
    "outputs/research/midtrend_daily_review_lite_and_badbuy_denominator_v1_20260628/"
    "bad_buy_denominator_events_canonical.csv"
)

INTERACTIONS = [
    "high_elasticity_quality_weak",
    "high_elasticity_deteriorating",
    "mainline_weak_quality_weak",
    "mainline_weak_deteriorating",
    "quality_weak_rank_edge",
    "quality_weak_weak_stock_excess",
    "quality_weak_weak_drawdown_quality",
]


def run_midtrend_fundamental_interaction_badbuy_research_cli(*, output_dir: str | Path) -> dict[str, Any]:
    events = pd.read_csv(DEFAULT_DENOMINATOR_EVENTS_PATH, low_memory=False) if DEFAULT_DENOMINATOR_EVENTS_PATH.exists() else pd.DataFrame()
    return run_midtrend_fundamental_interaction_badbuy_research_from_frames(
        denominator_events=events,
        output_dir=output_dir,
    )


def run_midtrend_fundamental_interaction_badbuy_research_from_frames(
    *,
    denominator_events: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    denominator = build_bad_buy_interaction_denominator(denominator_events)
    denominator.to_csv(output / "bad_buy_interaction_denominator.csv", index=False)

    contribution = build_bad_buy_interaction_net_contribution(denominator)
    contribution.to_csv(output / "bad_buy_interaction_net_contribution.csv", index=False)

    _single_interaction(denominator, "high_elasticity_quality_weak").to_csv(
        output / "high_elasticity_quality_weak_analysis.csv",
        index=False,
    )
    _single_interaction(denominator, "mainline_weak_quality_weak").to_csv(
        output / "mainline_weak_quality_weak_analysis.csv",
        index=False,
    )
    denominator[
        denominator["interaction_name"].isin(["high_elasticity_deteriorating", "mainline_weak_deteriorating"])
    ].to_csv(output / "deteriorating_quality_interaction_analysis.csv", index=False)

    (output / "fundamental_interaction_rule_candidates_research_only.md").write_text(
        _rule_candidates_md(contribution),
        encoding="utf-8",
    )
    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(), encoding="utf-8")
    (output / "final_interpretation.md").write_text(_final_interpretation(contribution), encoding="utf-8")
    return {"paths": {"output_dir": str(output)}}


def build_bad_buy_interaction_denominator(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["interaction_name"])
    frame = events.copy()
    frame["_quality"] = frame.get("canonical_fundamental_quality_bucket", "").astype(str)
    frame["_momentum"] = frame.get("canonical_fundamental_momentum_bucket", "").astype(str)
    frame["_high_elasticity"] = _bool(frame.get("high_elasticity_watch", False))
    frame["_mainline_confirmed"] = _bool(frame.get("mainline_confirmed", False))
    frame["_rank"] = _num(frame.get("score_rank", frame.get("current_rank", pd.Series(np.nan, index=frame.index))))
    frame["_stock_excess"] = _num(frame.get("stock_excess_ret_20_score", pd.Series(np.nan, index=frame.index)))
    frame["_drawdown"] = _num(frame.get("max_drawdown_20_score", pd.Series(np.nan, index=frame.index)))

    masks = {
        "high_elasticity_quality_weak": frame["_high_elasticity"] & frame["_quality"].eq("quality_weak"),
        "high_elasticity_deteriorating": frame["_high_elasticity"] & frame["_momentum"].eq("deteriorating"),
        "mainline_weak_quality_weak": ~frame["_mainline_confirmed"] & frame["_quality"].eq("quality_weak"),
        "mainline_weak_deteriorating": ~frame["_mainline_confirmed"] & frame["_momentum"].eq("deteriorating"),
        "quality_weak_rank_edge": frame["_quality"].eq("quality_weak") & frame["_rank"].gt(20),
        "quality_weak_weak_stock_excess": frame["_quality"].eq("quality_weak") & frame["_stock_excess"].lt(70),
        "quality_weak_weak_drawdown_quality": frame["_quality"].eq("quality_weak") & frame["_drawdown"].lt(55),
    }
    rows = []
    for name, mask in masks.items():
        part = frame[mask].copy()
        if part.empty:
            part = frame.iloc[:0].copy()
        part["interaction_name"] = name
        rows.append(part)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["interaction_name"])


def build_bad_buy_interaction_net_contribution(denominator: pd.DataFrame) -> pd.DataFrame:
    if denominator.empty:
        return pd.DataFrame(columns=["interaction_name"])
    rows = []
    for name, part in denominator.groupby("interaction_name", dropna=False):
        ret = _num(part.get("trade_return", pd.Series(dtype=float)))
        contribution = _num(part.get("contribution", pd.Series(dtype=float))).fillna(0)
        is_bad = _bool(part.get("is_bad_buy", False))
        is_winner = _bool(part.get("is_winner", False))
        sample = len(part)
        winner_contribution = float(contribution[contribution.gt(0)].sum())
        net = float(contribution.sum())
        rows.append(
            {
                "interaction_name": name,
                "sample_count": int(sample),
                "bad_buy_count": int(is_bad.sum()),
                "bad_buy_rate": float(is_bad.mean()) if sample else 0.0,
                "winner_count": int(is_winner.sum()),
                "winner_rate": float(is_winner.mean()) if sample else 0.0,
                "winner_contribution": winner_contribution,
                "loser_contribution": float(contribution[contribution.lt(0)].sum()),
                "net_bucket_contribution": net,
                "weighted_bad_buy_loss": float(_num(part.get("weighted_bad_buy_loss", pd.Series(dtype=float))).fillna(0).sum()),
                "avg_trade_return": float(ret.mean()) if ret.notna().any() else np.nan,
                "worst_loss": float(ret.min()) if ret.notna().any() else np.nan,
                "left_tail_10_loss": float(ret.sort_values().head(10).sum()) if ret.notna().any() else 0.0,
                "rule_readiness": _rule_readiness(sample, float(is_bad.mean()) if sample else 0.0, net, winner_contribution),
            }
        )
    return pd.DataFrame(rows).sort_values(["rule_readiness", "bad_buy_rate"], ascending=[True, False])


def _rule_readiness(sample_count: int, bad_buy_rate: float, net_contribution: float, winner_contribution: float) -> str:
    if sample_count <= 0:
        return "NOT_READY"
    if bad_buy_rate >= 0.65 and net_contribution < 0 and winner_contribution <= abs(net_contribution):
        return "CANDIDATE_FOR_SMALL_EXPERIMENT"
    if bad_buy_rate >= 0.55 and net_contribution < 0:
        return "RESEARCH_ONLY"
    return "NOT_READY"


def _single_interaction(denominator: pd.DataFrame, name: str) -> pd.DataFrame:
    return denominator[denominator["interaction_name"].eq(name)].copy() if not denominator.empty else denominator


def _rule_candidates_md(contribution: pd.DataFrame) -> str:
    lines = [
        "# Fundamental Interaction Rule Candidates",
        "",
        "All candidates are RESEARCH_ONLY. No strategy rule is implemented here.",
        "",
        "| interaction | sample_count | bad_buy_rate | net_contribution | winner_contribution | status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for _, row in contribution.iterrows():
        lines.append(
            f"| {row['interaction_name']} | {int(row['sample_count'])} | {float(row['bad_buy_rate']):.4f} | "
            f"{float(row['net_bucket_contribution']):.6f} | {float(row['winner_contribution']):.6f} | "
            f"{row['rule_readiness']} |"
        )
    lines.append("")
    lines.append("Do not implement `quality_weak no-buy`; only a narrow interaction can advance if it has high bad_buy_rate, negative net contribution, low winner contribution, heavy left tail, and sufficient sample size.")
    return "\n".join(lines) + "\n"


def _final_interpretation(contribution: pd.DataFrame) -> str:
    candidates = contribution[contribution["rule_readiness"].astype(str).eq("CANDIDATE_FOR_SMALL_EXPERIMENT")] if not contribution.empty else pd.DataFrame()
    lines = [
        "# Final Interpretation",
        "",
        "1. This package studies interaction risk only; it does not change strategy logic.",
        "2. Single quality buckets remain rejected as entry gates.",
        f"3. Candidate interactions passing the strict screen: {len(candidates)}.",
        "4. A future experiment is allowed only for the narrowest harmful interaction, not for broad `quality_weak no-buy`.",
        "5. Re-entry, slow exit, carry, and ownership hold remain rejected/research-only.",
    ]
    return "\n".join(lines) + "\n"


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "denominator_events_path", "value": str(DEFAULT_DENOMINATOR_EVENTS_PATH)},
            {"param": "rank_edge_threshold", "value": 20},
            {"param": "stock_excess_weak_threshold", "value": 70},
            {"param": "drawdown_quality_weak_threshold", "value": 55},
            {"param": "strategy_changes", "value": "none"},
        ]
    )


def _code_audit() -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- runner: `stock_research.midtrend_fundamental_interaction_badbuy_research_v1`",
            "- input: canonical bad-buy denominator events",
            "- outputs are research-only interaction diagnostics",
            "- no trading strategy logic changed",
        ]
    ) + "\n"


def _bool(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.astype(str).str.lower().isin(["true", "1", "yes"])
    return pd.Series([bool(value)])


def _num(value: Any) -> pd.Series:
    return pd.to_numeric(value, errors="coerce")
