from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


MAINLINE_DIAGNOSTIC_COLUMNS = [
    "rebalance_month",
    "rebalance_date",
    "industry_name",
    "market_regime",
    "industry_mainline_score_v1",
    "mainline_persistence_score",
    "mainline_amount_quality_score",
    "mainline_candidate_quality_score",
    "mainline_breadth_quality_score",
    "mainline_expansion_quality_score",
    "mainline_overheat_risk",
    "mainline_concentration_risk",
    "mainline_tag",
    "industry_focus_score_v2",
    "future_20d_return",
    "future_20d_excess_return",
    "future_20d_rank",
    "future_20d_max_drawdown",
]


def build_market_regime_diagnostics(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_diagnostics(diagnostics)
    columns = [
        "rebalance_date",
        "rebalance_month",
        "market_regime",
        "industry_count",
        "score_spread",
        "top3_score_share",
        "top3_mainline_score",
        "top3_breadth_score",
        "top3_overheat_penalty",
        "median_industry_excess_ret_20d",
        "median_breadth",
        "median_overheat_penalty",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for trade_date, group in frame.groupby("rebalance_date", sort=True):
        scores = pd.to_numeric(group["industry_focus_score_v2"], errors="coerce").fillna(0.0)
        shifted = scores - scores.min()
        total_shifted = float(shifted.sum())
        top3_share = float(shifted.sort_values(ascending=False).head(3).sum() / total_shifted) if total_shifted > 0 else 0.0
        score_spread = float(scores.max() - scores.median()) if not scores.empty else 0.0
        top_count = max(1, min(3, int(round(len(group) * 0.06))))
        top3 = group.assign(_score=scores).sort_values("_score", ascending=False).head(top_count)
        top3_score = float(top3["_score"].mean()) if not top3.empty else 0.0
        top3_breadth = _mean_first_available(
            top3,
            ["breadth_expansion_score", "up_ratio_20d"],
        )
        top3_overheat = _mean(top3, "overheat_penalty")
        median_excess = _median(group, "industry_excess_ret_20d")
        median_breadth = _median_first_available(group, ["breadth_expansion_score", "up_ratio_20d"])
        median_overheat = _median(group, "overheat_penalty")

        if median_excess < -0.02 and float(scores.max()) < 0.35:
            regime = "weak_market"
        elif score_spread >= 0.25 and top3_breadth >= 0.60 and top3_overheat <= 0.58:
            regime = "mainline"
        elif median_breadth >= 0.55 and score_spread < 0.30:
            regime = "broad_market"
        else:
            regime = "rotation"

        rows.append(
            {
                "rebalance_date": trade_date,
                "rebalance_month": str(pd.Timestamp(trade_date).to_period("M")),
                "market_regime": regime,
                "industry_count": int(group["industry_name"].nunique()),
                "score_spread": score_spread,
                "top3_score_share": top3_share,
                "top3_mainline_score": top3_score,
                "top3_breadth_score": top3_breadth,
                "top3_overheat_penalty": top3_overheat,
                "median_industry_excess_ret_20d": median_excess,
                "median_breadth": median_breadth,
                "median_overheat_penalty": median_overheat,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_industry_mainline_scores(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_diagnostics(diagnostics)
    if frame.empty:
        return pd.DataFrame(columns=MAINLINE_DIAGNOSTIC_COLUMNS)

    result = frame.copy()
    result["mainline_persistence_score"] = _component_or_rank(
        result,
        "trend_persistence_score",
        [
            "industry_ret_5d",
            "industry_ret_10d",
            "industry_ret_20d",
            "industry_excess_ret_5d",
            "industry_excess_ret_10d",
            "industry_excess_ret_20d",
        ],
    )
    result["mainline_amount_quality_score"] = _amount_quality_score(result)
    result["mainline_candidate_quality_score"] = _component_or_rank(
        result,
        "candidate_density_score",
        ["top20_density", "top50_density", "top100_density"],
    )
    result["mainline_breadth_quality_score"] = _component_or_rank(
        result,
        "breadth_expansion_score",
        ["up_ratio_20d", "excess_up_ratio_20d", "breadth_expansion_score"],
    )
    result["mainline_expansion_quality_score"] = _component_or_rank(
        result,
        "leader_to_middle_expansion_score",
        ["leader_to_middle_expansion_score", "middle_ret_20d"],
    )
    result["mainline_overheat_risk"] = pd.to_numeric(
        result.get("overheat_penalty", 0.0),
        errors="coerce",
    ).fillna(0.0)
    result["mainline_concentration_risk"] = pd.to_numeric(
        result.get("concentration_penalty", 0.0),
        errors="coerce",
    ).fillna(0.0)
    result["industry_mainline_score_v1"] = (
        0.30 * result["mainline_persistence_score"]
        + 0.15 * result["mainline_amount_quality_score"]
        + 0.20 * result["mainline_candidate_quality_score"]
        + 0.20 * result["mainline_breadth_quality_score"]
        + 0.15 * result["mainline_expansion_quality_score"]
        - 0.25 * result["mainline_overheat_risk"]
        - 0.20 * result["mainline_concentration_risk"]
    )
    result["mainline_tag"] = result.apply(_mainline_tag, axis=1)
    return result


def build_regime_effectiveness(
    scored: pd.DataFrame,
    regimes: pd.DataFrame,
    *,
    buckets: int = 5,
) -> pd.DataFrame:
    if scored.empty or regimes.empty:
        return pd.DataFrame(
            columns=[
                "market_regime",
                "score_bucket",
                "sample_count",
                "avg_future_20d_return",
                "median_future_20d_return",
                "avg_future_20d_excess_return",
                "win_rate_vs_market",
                "avg_future_20d_rank",
                "avg_future_20d_max_drawdown",
            ]
        )
    frame = scored.merge(
        regimes[["rebalance_date", "market_regime"]],
        on="rebalance_date",
        how="left",
        suffixes=("", "_regime"),
    )
    if "market_regime_regime" in frame.columns:
        frame["market_regime"] = frame["market_regime"].fillna(frame["market_regime_regime"])
    frame["score_bucket"] = _quantile_bucket(frame["industry_mainline_score_v1"], buckets)
    grouped = frame.groupby(["market_regime", "score_bucket"], dropna=False)
    return grouped.apply(_future_stats, include_groups=False).reset_index()


def build_mainline_tag_effectiveness(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(
            columns=[
                "mainline_tag",
                "sample_count",
                "avg_future_20d_return",
                "median_future_20d_return",
                "avg_future_20d_excess_return",
                "win_rate_vs_market",
                "avg_future_20d_rank",
                "avg_future_20d_max_drawdown",
            ]
        )
    return scored.groupby("mainline_tag", dropna=False).apply(
        _future_stats,
        include_groups=False,
    ).reset_index()


def run_industry_mainline_regime_diagnostics(
    *,
    diagnostics_path: str | Path,
    start_date: object,
    end_date: object,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
) -> dict[str, Any]:
    diagnostics = pd.read_csv(diagnostics_path)
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    diagnostics = _normalize_diagnostics(diagnostics)
    diagnostics = diagnostics[
        (diagnostics["rebalance_date"] >= start)
        & (diagnostics["rebalance_date"] <= end)
    ].copy()

    regimes = build_market_regime_diagnostics(diagnostics)
    scored = build_industry_mainline_scores(diagnostics)
    scored = scored.merge(
        regimes[["rebalance_date", "market_regime"]],
        on="rebalance_date",
        how="left",
    )
    regime_effectiveness = build_regime_effectiveness(scored, regimes)
    tag_effectiveness = build_mainline_tag_effectiveness(scored)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "diagnostics": str(output / "industry_mainline_regime_diagnostics.csv"),
        "market_regimes": str(output / "market_regime_diagnostics.csv"),
        "regime_effectiveness": str(output / "market_regime_industry_effectiveness.csv"),
        "tag_effectiveness": str(output / "industry_mainline_tag_effectiveness.csv"),
        "markdown_report": str(output / "industry_mainline_regime_report.md"),
    }
    scored.reindex(columns=MAINLINE_DIAGNOSTIC_COLUMNS).to_csv(paths["diagnostics"], index=False)
    regimes.to_csv(paths["market_regimes"], index=False)
    regime_effectiveness.to_csv(paths["regime_effectiveness"], index=False)
    tag_effectiveness.to_csv(paths["tag_effectiveness"], index=False)
    write_industry_mainline_report(
        path=paths["markdown_report"],
        start_date=start,
        end_date=end,
        regimes=regimes,
        regime_effectiveness=regime_effectiveness,
        tag_effectiveness=tag_effectiveness,
    )
    return {
        "paths": paths,
        "diagnostics": scored,
        "market_regimes": regimes,
        "regime_effectiveness": regime_effectiveness,
        "tag_effectiveness": tag_effectiveness,
    }


def write_industry_mainline_report(
    *,
    path: str | Path,
    start_date: object,
    end_date: object,
    regimes: pd.DataFrame,
    regime_effectiveness: pd.DataFrame,
    tag_effectiveness: pd.DataFrame,
) -> None:
    lines = [
        "# 行业主线 Regime 诊断报告",
        "",
        "## 1. 研究范围",
        f"- 区间：{_iso_date(start_date)} 至 {_iso_date(end_date)}",
        "- 目的：判断行业因子在哪些市场环境下可用，本阶段不接交易策略、不调参。",
        "- 约束：regime 与 mainline score 不使用 future_20d_* 字段；future 字段只用于事后有效性检验。",
        "",
        "## 2. 市场 Regime 分布",
        _table_or_empty(regimes["market_regime"].value_counts().rename_axis("market_regime").reset_index(name="days")),
        "",
        "## 3. Regime 条件下的行业主线有效性",
        _table_or_empty(regime_effectiveness),
        "",
        "## 4. Mainline 标签有效性",
        _table_or_empty(tag_effectiveness),
        "",
        "## 5. 下一步",
        "- 只有当 mainline regime 下高分桶未来超额更强时，才考虑接入软约束回测。",
        "- 若 rotation/weak_market 下高分桶无效或反向，应在策略层自动降权行业因子。",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normalize_diagnostics(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = diagnostics.copy()
    if "rebalance_date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "rebalance_date"})
    if "rebalance_date" not in frame.columns:
        frame["rebalance_date"] = ""
    frame["rebalance_date"] = frame["rebalance_date"].map(_iso_date)
    if "rebalance_month" not in frame.columns:
        frame["rebalance_month"] = pd.to_datetime(frame["rebalance_date"]).dt.to_period("M").astype(str)
    if "industry_name" not in frame.columns:
        frame["industry_name"] = ""
    for col in [
        "industry_focus_score_v2",
        "industry_ret_5d",
        "industry_ret_10d",
        "industry_ret_20d",
        "industry_excess_ret_5d",
        "industry_excess_ret_10d",
        "industry_excess_ret_20d",
        "industry_amount_share_change_5d_vs_20d",
        "industry_amount_share_5d",
        "industry_amount_share_20d",
        "trend_persistence_score",
        "amount_share_score",
        "candidate_density_score",
        "top20_density",
        "top50_density",
        "top100_density",
        "up_ratio_20d",
        "excess_up_ratio_20d",
        "breadth_expansion_score",
        "leader_to_middle_expansion_score",
        "middle_ret_20d",
        "overheat_penalty",
        "concentration_penalty",
        "future_20d_return",
        "future_20d_excess_return",
        "future_20d_rank",
        "future_20d_max_drawdown",
    ]:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    return frame


def _rank_component(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    available = []
    for col in columns:
        if col in frame.columns:
            values = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
            available.append(values.groupby(frame["rebalance_date"]).rank(pct=True, method="average"))
    if not available:
        return pd.Series(0.0, index=frame.index)
    return pd.concat(available, axis=1).mean(axis=1).fillna(0.0)


def _component_or_rank(frame: pd.DataFrame, component_col: str, fallback_cols: list[str]) -> pd.Series:
    if component_col in frame.columns:
        values = pd.to_numeric(frame[component_col], errors="coerce")
        if values.notna().any() and values.abs().sum() > 0:
            return values.fillna(0.0)
    return _rank_component(frame, fallback_cols)


def _amount_quality_score(frame: pd.DataFrame) -> pd.Series:
    if "amount_share_score" in frame.columns:
        stable_share = pd.to_numeric(frame["amount_share_score"], errors="coerce").fillna(0.0)
    else:
        stable_share = _rank_component(frame, ["industry_amount_share_5d", "industry_amount_share_20d"])
    change = pd.to_numeric(
        frame.get("industry_amount_share_change_5d_vs_20d", 0.0),
        errors="coerce",
    ).fillna(0.0)
    moderate_change = 1.0 - (change - 0.15).abs().clip(upper=0.40) / 0.40
    moderate_change = moderate_change.clip(lower=0.0, upper=1.0)
    return (0.60 * stable_share + 0.40 * moderate_change).fillna(0.0)


def _mainline_tag(row: pd.Series) -> str:
    score = float(row["industry_mainline_score_v1"])
    persistence = float(row["mainline_persistence_score"])
    breadth = float(row["mainline_breadth_quality_score"])
    overheat = float(row["mainline_overheat_risk"])
    concentration = float(row["mainline_concentration_risk"])
    amount = float(row["mainline_amount_quality_score"])
    if overheat >= 0.75 and score > 0.20:
        return "overheated_mainline"
    if concentration >= 0.45 and score > 0.20:
        return "narrow_leader_only"
    if amount >= 0.65 and persistence < 0.45:
        return "amount_spike_not_sustained"
    if score >= 0.35 and persistence >= 0.55 and breadth >= 0.50:
        return "sustained_mainline"
    return "neutral"


def _future_stats(frame: pd.DataFrame) -> pd.Series:
    future_return = pd.to_numeric(frame["future_20d_return"], errors="coerce")
    future_excess = pd.to_numeric(frame["future_20d_excess_return"], errors="coerce")
    future_rank = pd.to_numeric(frame["future_20d_rank"], errors="coerce")
    future_drawdown = pd.to_numeric(frame["future_20d_max_drawdown"], errors="coerce")
    return pd.Series(
        {
            "sample_count": int(len(frame)),
            "avg_future_20d_return": float(future_return.mean()) if len(frame) else 0.0,
            "median_future_20d_return": float(future_return.median()) if len(frame) else 0.0,
            "avg_future_20d_excess_return": float(future_excess.mean()) if len(frame) else 0.0,
            "win_rate_vs_market": float((future_excess > 0).mean()) if len(frame) else 0.0,
            "avg_future_20d_rank": float(future_rank.mean()) if len(frame) else 0.0,
            "avg_future_20d_max_drawdown": float(future_drawdown.mean()) if len(frame) else 0.0,
        }
    )


def _quantile_bucket(values: pd.Series, buckets: int) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    unique_count = int(numeric.nunique())
    if unique_count <= 1:
        return pd.Series(1, index=values.index)
    q = max(1, min(int(buckets), unique_count))
    return pd.qcut(numeric, q=q, labels=False, duplicates="drop").astype(int) + 1


def _median(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).median())


def _median_first_available(frame: pd.DataFrame, columns: list[str]) -> float:
    for col in columns:
        if col in frame.columns:
            return _median(frame, col)
    return 0.0


def _mean(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).mean())


def _mean_first_available(frame: pd.DataFrame, columns: list[str]) -> float:
    for col in columns:
        if col in frame.columns:
            return _mean(frame, col)
    return 0.0


def _iso_date(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def _table_or_empty(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No data."
    return frame.to_markdown(index=False)
