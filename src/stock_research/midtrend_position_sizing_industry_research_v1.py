from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TOP10_DIR = Path("outputs/research/current_mid_trend_strategy_v2_top10_candidate_20250101_20260612")


def run_midtrend_position_sizing_industry_research_cli(*, output_dir: str | Path) -> dict[str, Any]:
    return run_midtrend_position_sizing_industry_research_from_frames(
        holdings=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv"),
        trades=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_trade_changes.csv"),
        industry_exposure=_optional_csv(TOP10_DIR / "current_mid_trend_strategy_v2_top10_candidate_industry_exposure.csv"),
        output_dir=output_dir,
    )


def run_midtrend_position_sizing_industry_research_from_frames(
    *,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    industry_exposure: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    proxy_source = trades if "forward_return" in trades.columns and not trades.empty else holdings
    proxy = build_position_sizing_proxy_comparison(proxy_source)
    proxy.to_csv(output / "position_sizing_proxy_comparison.csv", index=False)
    rank_diag = build_rank_decay_weight_diagnostics(holdings)
    rank_diag.to_csv(output / "rank_decay_weight_diagnostics.csv", index=False)
    vol_diag = build_volatility_cap_weight_diagnostics(holdings)
    vol_diag.to_csv(output / "volatility_cap_weight_diagnostics.csv", index=False)
    concentration = build_industry_concentration_diagnostics(holdings, trades)
    concentration.to_csv(output / "industry_concentration_diagnostics.csv", index=False)
    contribution = build_industry_contribution_summary(trades, industry_exposure)
    contribution.to_csv(output / "industry_contribution_summary.csv", index=False)
    (output / "industry_concentration_rule_candidates_research_only.md").write_text(
        _rule_candidates_md(proxy, concentration),
        encoding="utf-8",
    )
    _run_params().to_csv(output / "run_params.csv", index=False)
    (output / "code_audit.md").write_text(_code_audit(), encoding="utf-8")
    (output / "final_interpretation.md").write_text(_final_interpretation(proxy, concentration), encoding="utf-8")
    return {"paths": {"output_dir": str(output)}}


def build_position_sizing_proxy_comparison(holdings: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_holdings(holdings)
    rows = []
    for name, weight in {
        "top10_equal_weight": _equal_weight(frame),
        "top10_rank_decay": _rank_decay_weight(frame),
        "top10_volatility_cap": _volatility_cap_weight(frame),
    }.items():
        contribution = _forward_return(frame) * weight
        rows.append(
            {
                "proxy_name": name,
                "sample_count": int(len(frame)),
                "avg_weight": float(weight.mean()) if len(weight) else np.nan,
                "max_weight": float(weight.max()) if len(weight) else np.nan,
                "proxy_contribution": float(contribution.sum()),
                "winner_contribution": float(contribution[contribution.gt(0)].sum()),
                "loser_contribution": float(contribution[contribution.lt(0)].sum()),
                "research_only": True,
            }
        )
    return pd.DataFrame(rows, dtype=object)


def build_rank_decay_weight_diagnostics(holdings: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_holdings(holdings)
    frame["rank_decay_weight"] = _rank_decay_weight(frame)
    return frame[["trade_date", "asset_id", "industry_name", "final_slot_rank", "target_weight", "rank_decay_weight"]].copy()


def build_volatility_cap_weight_diagnostics(holdings: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_holdings(holdings)
    frame["volatility_cap_weight"] = _volatility_cap_weight(frame)
    return frame[["trade_date", "asset_id", "industry_name", "volatility_20_score", "target_weight", "volatility_cap_weight"]].copy()


def build_industry_concentration_diagnostics(holdings: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    h = _prepare_holdings(holdings)
    if h.empty:
        return pd.DataFrame(columns=["industry_name", "holding_count", "industry_weight", "industry_contribution"])
    t = trades.copy()
    if not t.empty:
        t["contribution"] = _forward_return(t) * _num(t.get("target_weight", pd.Series(1.0, index=t.index))).fillna(1.0)
    contribution = (
        t.groupby("industry_name", dropna=False)["contribution"].sum()
        if not t.empty and "industry_name" in t.columns
        else pd.Series(dtype=float)
    )
    grouped = h.groupby("industry_name", dropna=False).agg(
        holding_count=("asset_id", "count"),
        industry_weight=("target_weight", "sum"),
        avg_slot=("final_slot_rank", "mean"),
    )
    if "trade_date" in h.columns:
        daily_counts = h.groupby(["industry_name", "trade_date"], dropna=False)["asset_id"].count()
        grouped["avg_daily_holding_count"] = daily_counts.groupby(level=0).mean()
        grouped["max_daily_holding_count"] = daily_counts.groupby(level=0).max()
    else:
        grouped["avg_daily_holding_count"] = grouped["holding_count"]
        grouped["max_daily_holding_count"] = grouped["holding_count"]
    grouped["industry_contribution"] = grouped.index.map(contribution).fillna(0.0)
    grouped["industry_weight"] = grouped["industry_weight"].round(10)
    grouped["industry_contribution"] = grouped["industry_contribution"].round(10)
    grouped["crowding_bucket"] = pd.cut(
        grouped["max_daily_holding_count"],
        bins=[-1, 2, 4, 99],
        labels=["low", "medium", "high"],
    ).astype(str)
    return grouped.reset_index().sort_values(["industry_weight", "holding_count"], ascending=False)


def build_industry_contribution_summary(trades: pd.DataFrame, industry_exposure: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    if frame.empty:
        return pd.DataFrame(columns=["industry_name", "trade_count", "industry_contribution"])
    frame["contribution"] = _forward_return(frame) * _num(frame.get("target_weight", pd.Series(1.0, index=frame.index))).fillna(1.0)
    summary = frame.groupby("industry_name", dropna=False).agg(
        trade_count=("asset_id", "count"),
        industry_contribution=("contribution", "sum"),
        winner_rate=("contribution", lambda value: float((value > 0).mean()) if len(value) else 0.0),
    ).reset_index()
    if not industry_exposure.empty and "industry_name" in industry_exposure.columns:
        exposure = industry_exposure.groupby("industry_name", dropna=False).size().rename("exposure_rows").reset_index()
        summary = summary.merge(exposure, on="industry_name", how="left")
    return summary.sort_values("industry_contribution", ascending=False)


def _prepare_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    frame = holdings.copy()
    if frame.empty:
        return frame
    if "target_weight" not in frame.columns:
        frame["target_weight"] = 1.0 / 10.0
    if "final_slot_rank" not in frame.columns:
        frame["final_slot_rank"] = frame.get("score_rank", pd.Series(np.nan, index=frame.index))
    if "industry_name" not in frame.columns:
        frame["industry_name"] = "unknown"
    if "volatility_20_score" not in frame.columns:
        frame["volatility_20_score"] = np.nan
    return frame


def _equal_weight(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    per_day = frame.groupby("trade_date")["asset_id"].transform("count") if "trade_date" in frame.columns else len(frame)
    return 1.0 / pd.Series(per_day, index=frame.index).replace(0, np.nan)


def _rank_decay_weight(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    rank = _num(frame.get("final_slot_rank", pd.Series(np.nan, index=frame.index))).fillna(10)
    raw = (11 - rank).clip(lower=1)
    total = raw.groupby(frame.get("trade_date", pd.Series("all", index=frame.index))).transform("sum")
    return raw / total


def _volatility_cap_weight(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    base = _equal_weight(frame)
    vol = _num(frame.get("volatility_20_score", pd.Series(np.nan, index=frame.index))).fillna(50)
    cap = np.where(vol < 30, 0.5, 1.0)
    raw = base * cap
    total = raw.groupby(frame.get("trade_date", pd.Series("all", index=frame.index))).transform("sum")
    return raw / total


def _forward_return(frame: pd.DataFrame) -> pd.Series:
    for column in ["forward_return", "trade_return", "return"]:
        if column in frame.columns:
            return _num(frame[column]).fillna(0)
    return pd.Series(0.0, index=frame.index)


def _num(value: Any) -> pd.Series:
    return pd.to_numeric(value, errors="coerce")


def _rule_candidates_md(proxy: pd.DataFrame, concentration: pd.DataFrame) -> str:
    lines = [
        "# Position Sizing And Industry Rule Candidates",
        "",
        "All ideas below are RESEARCH_ONLY. No position sizing or industry cap rule is implemented.",
        "",
        "Potential future checks:",
        "- rank decay weight: RESEARCH_ONLY until stability and drawdown improve over equal weight.",
        "- volatility cap: RESEARCH_ONLY until it preserves winner contribution.",
        "- industry cap: RESEARCH_ONLY until concentration is proven to worsen drawdown/net contribution.",
        "",
        proxy.to_markdown(index=False) if not proxy.empty else "",
        "",
        concentration.head(20).to_markdown(index=False) if not concentration.empty else "",
    ]
    return "\n".join(lines) + "\n"


def _final_interpretation(proxy: pd.DataFrame, concentration: pd.DataFrame) -> str:
    best = proxy.sort_values("proxy_contribution", ascending=False).iloc[0]["proxy_name"] if not proxy.empty else "n/a"
    max_industry = concentration.iloc[0]["industry_name"] if not concentration.empty else "n/a"
    lines = [
        "# Final Interpretation",
        "",
        "1. This package is research-only and does not alter target weights.",
        f"2. Best proxy contribution in this diagnostic: {best}.",
        f"3. Largest concentration industry by weight/count: {max_industry}.",
        "4. Do not promote rank decay, volatility cap, or industry cap without separate strategy backtest acceptance.",
    ]
    return "\n".join(lines) + "\n"


def _run_params() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"param": "top10_dir", "value": str(TOP10_DIR)},
            {"param": "strategy_changes", "value": "none"},
        ]
    )


def _code_audit() -> str:
    return "\n".join(
        [
            "# Code Audit",
            "",
            "- runner: `stock_research.midtrend_position_sizing_industry_research_v1`",
            "- consumes accepted top10 holdings/trades",
            "- outputs proxy diagnostics only",
            "- no trading strategy logic changed",
        ]
    ) + "\n"


def _optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
