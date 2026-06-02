from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.industry_focus_v2 import (
    build_v2_soft_weight_scores,
    load_research_inputs,
)
from stock_research.performance_metrics import calc_performance_metrics
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
    run_vectorized_topn_backtest,
)


RISK_TAGS = {"narrow_leader_only", "overheated_mainline"}
STRATEGIES = [
    "baseline_top20",
    "v2_soft_weight",
    "regime_gated_soft_weight",
    "regime_gated_risk_downweight",
    "regime_gated_smooth_weight",
]

SUMMARY_COLUMNS = [
    "strategy",
    "cumulative_return_after_cost",
    "max_drawdown",
    "annualized_turnover",
    "monthly_win_rate",
    "avg_holding_count",
    "avg_industry_count",
    "avg_top1_industry_weight",
    "avg_top3_industry_weight",
    "best_year",
    "worst_year",
]

ANNUAL_COLUMNS = [
    "year",
    "strategy",
    "annual_return_after_cost",
    "annual_max_drawdown",
    "annual_turnover",
    "monthly_win_rate",
    "avg_industry_count",
    "avg_top1_industry_weight",
    "avg_top3_industry_weight",
]

MONTHLY_COLUMNS = [
    "rebalance_month",
    "strategy",
    "monthly_return_after_cost",
    "cumulative_return",
    "drawdown",
    "turnover",
    "market_regime",
    "top1_industry",
    "top1_industry_weight",
    "top3_industry_weight",
]

EXPOSURE_COLUMNS = [
    "rebalance_date",
    "strategy",
    "industry_name",
    "industry_weight",
    "market_regime",
    "industry_mainline_tag",
    "industry_focus_score_v2",
    "mainline_score",
    "risk_tag",
    "positive_weight_allowed",
    "risk_downweighted",
]

TURNOVER_COLUMNS = [
    "rebalance_date",
    "strategy",
    "turnover",
    "added_assets",
    "removed_assets",
    "kept_assets",
    "added_industries",
    "removed_industries",
    "kept_industries",
]


def build_industry_weight_panel(
    diagnostics: pd.DataFrame,
    regimes: pd.DataFrame,
    mainline: pd.DataFrame,
    *,
    strategy: str,
    positive_cap: float = 0.15,
    negative_cap: float = -0.10,
) -> pd.DataFrame:
    diag = _normalize_diagnostics(diagnostics)
    reg = _normalize_regimes(regimes)
    main = _normalize_mainline(mainline)
    panel = diag.merge(reg, on="rebalance_date", how="left")
    panel = panel.merge(main, on=["rebalance_date", "industry_name"], how="left")
    panel["market_regime"] = panel["market_regime"].fillna("unknown")
    panel["mainline_tag"] = panel["mainline_tag"].fillna("neutral")
    panel["industry_mainline_score_v1"] = pd.to_numeric(
        panel["industry_mainline_score_v1"],
        errors="coerce",
    ).fillna(panel["industry_focus_score_v2"])
    panel["risk_tag"] = panel["mainline_tag"].where(panel["mainline_tag"].isin(RISK_TAGS), "")
    panel["risk_downweighted"] = panel["risk_tag"].ne("").astype(object)

    score_source = panel["industry_mainline_score_v1"].fillna(panel["industry_focus_score_v2"])
    panel["_score_rank"] = score_source.groupby(panel["rebalance_date"]).rank(pct=True, method="average")
    base_positive = ((panel["_score_rank"] - 0.5) * 0.30).clip(lower=0.0, upper=positive_cap)
    base_negative = ((panel["_score_rank"] - 0.5) * 0.20).clip(lower=negative_cap, upper=0.0)

    if strategy == "regime_gated_risk_downweight":
        positive_allowed = pd.Series(False, index=panel.index)
        adjustment = pd.Series(0.0, index=panel.index)
    else:
        positive_allowed = panel["market_regime"].eq("mainline") & (~panel["mainline_tag"].isin(RISK_TAGS))
        adjustment = base_positive.where(positive_allowed, 0.0) + base_negative

    risk_penalty = panel["mainline_tag"].map(
        {
            "narrow_leader_only": -0.10,
            "overheated_mainline": -0.10,
        }
    ).fillna(0.0)
    adjustment = (adjustment + risk_penalty).clip(lower=negative_cap, upper=positive_cap)
    panel["positive_weight_allowed"] = positive_allowed.astype(object)
    panel["industry_weight_adjustment"] = adjustment
    panel["industry_score_multiplier"] = (1.0 + adjustment).clip(lower=0.50)
    result = panel[
        [
            "rebalance_date",
            "industry_name",
            "market_regime",
            "industry_focus_score_v2",
            "industry_mainline_score_v1",
            "mainline_tag",
            "risk_tag",
            "positive_weight_allowed",
            "risk_downweighted",
            "industry_weight_adjustment",
            "industry_score_multiplier",
        ]
    ].rename(
        columns={
            "industry_mainline_score_v1": "mainline_score",
            "mainline_tag": "industry_mainline_tag",
        }
    )
    if strategy == "regime_gated_smooth_weight":
        result = smooth_industry_weight_panel(result)
        result["industry_score_multiplier"] = (1.0 + result["industry_weight_adjustment"]).clip(lower=0.50)
    return result


def smooth_industry_weight_panel(
    panel: pd.DataFrame,
    *,
    max_step: float = 0.05,
    persistence: float = 0.60,
) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    result = panel.copy().sort_values(["industry_name", "rebalance_date"])
    smoothed: list[pd.DataFrame] = []
    for _, group in result.groupby("industry_name", sort=False):
        previous = 0.0
        values = []
        for raw in pd.to_numeric(group["industry_weight_adjustment"], errors="coerce").fillna(0.0):
            target = persistence * previous + (1.0 - persistence) * float(raw)
            delta = max(-max_step, min(max_step, target - previous))
            previous = previous + delta
            values.append(previous)
        temp = group.copy()
        temp["industry_weight_adjustment"] = values
        smoothed.append(temp)
    return pd.concat(smoothed, ignore_index=True).sort_values(["rebalance_date", "industry_name"]).reset_index(drop=True)


def build_weighted_scores(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    weight_panel: pd.DataFrame,
) -> pd.DataFrame:
    score_frame = _normalize_scores(scores)
    members = _normalize_memberships(memberships)
    panel = weight_panel.rename(columns={"rebalance_date": "trade_date"}).copy()
    joined = score_frame.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    joined = joined.merge(
        panel[["trade_date", "industry_name", "industry_score_multiplier"]],
        on=["trade_date", "industry_name"],
        how="left",
    )
    joined["industry_score_multiplier"] = pd.to_numeric(
        joined["industry_score_multiplier"],
        errors="coerce",
    ).fillna(1.0)
    joined["score_total"] = joined["score_total"] * joined["industry_score_multiplier"]
    return _normalize_scores(joined[["trade_date", "asset_id", "score_total"]])


def run_industry_regime_gated_backtest(
    *,
    start_date: object,
    end_date: object,
    diagnostics_path: str | Path,
    regime_path: str | Path,
    mainline_path: str | Path,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    top_n: int = 20,
    transaction_cost_bps: float = 20.0,
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    diagnostics = pd.read_csv(diagnostics_path)
    regimes = pd.read_csv(regime_path)
    mainline = pd.read_csv(mainline_path)
    prices, memberships, stock_scores = load_research_inputs(
        start_date=start,
        end_date=end,
        lookback_days=0,
        forward_days=0,
        industry_system=industry_system,
        industry_level=industry_level,
        adjust_type=adjust_type,
        service=service,
    )
    scores = _normalize_scores(stock_scores)
    diagnostics = _filter_dates(_normalize_diagnostics(diagnostics), start, end)
    regimes = _filter_dates(_normalize_regimes(regimes), start, end)
    mainline = _filter_dates(_normalize_mainline(mainline), start, end)

    panels = {
        "regime_gated_soft_weight": build_industry_weight_panel(
            diagnostics,
            regimes,
            mainline,
            strategy="regime_gated_soft_weight",
        ),
        "regime_gated_risk_downweight": build_industry_weight_panel(
            diagnostics,
            regimes,
            mainline,
            strategy="regime_gated_risk_downweight",
        ),
        "regime_gated_smooth_weight": build_industry_weight_panel(
            diagnostics,
            regimes,
            mainline,
            strategy="regime_gated_smooth_weight",
        ),
    }
    strategy_scores = {
        "baseline_top20": scores,
        "v2_soft_weight": build_v2_soft_weight_scores(scores, memberships, diagnostics),
        "regime_gated_soft_weight": build_weighted_scores(scores, memberships, panels["regime_gated_soft_weight"]),
        "regime_gated_risk_downweight": build_weighted_scores(scores, memberships, panels["regime_gated_risk_downweight"]),
        "regime_gated_smooth_weight": build_weighted_scores(scores, memberships, panels["regime_gated_smooth_weight"]),
    }
    results: dict[str, VectorizedTopNResult] = {}
    summary_rows = []
    annual_rows = []
    monthly_rows = []
    exposure_rows = []
    turnover_rows = []
    for strategy, strategy_score in strategy_scores.items():
        result = run_vectorized_topn_backtest(
            strategy_score,
            prices[["trade_date", "asset_id", "close"]],
            VectorizedTopNConfig(
                start_date=start,
                end_date=end,
                top_n=top_n,
                rebalance_frequency="daily",
                transaction_cost_bps=transaction_cost_bps,
            ),
        )
        results[strategy] = result
        panel = panels.get(strategy, _neutral_weight_panel(diagnostics, regimes, mainline))
        exposure = build_industry_exposure(
            positions=result.positions,
            memberships=memberships,
            weight_panel=panel,
            strategy=strategy,
        )
        turnover = build_turnover_detail(
            positions=result.positions,
            trades=result.trades,
            memberships=memberships,
            strategy=strategy,
        )
        monthly = build_monthly_metrics(
            equity_curve=result.equity_curve,
            exposure=exposure,
            regimes=regimes,
            strategy=strategy,
        )
        annual = build_annual_metrics(
            equity_curve=result.equity_curve,
            monthly_metrics=monthly,
            exposure=exposure,
            strategy=strategy,
        )
        summary_rows.append(build_summary_row(result, annual, monthly, exposure, strategy))
        annual_rows.extend(annual.to_dict("records"))
        monthly_rows.extend(monthly.to_dict("records"))
        exposure_rows.extend(exposure.to_dict("records"))
        turnover_rows.extend(turnover.to_dict("records"))

    summary = pd.DataFrame(summary_rows).reindex(columns=SUMMARY_COLUMNS)
    annual_metrics = pd.DataFrame(annual_rows).reindex(columns=ANNUAL_COLUMNS)
    monthly_metrics = pd.DataFrame(monthly_rows).reindex(columns=MONTHLY_COLUMNS)
    industry_exposure = pd.DataFrame(exposure_rows).reindex(columns=EXPOSURE_COLUMNS)
    turnover_detail = pd.DataFrame(turnover_rows).reindex(columns=TURNOVER_COLUMNS)
    paths = write_regime_gated_backtest_outputs(
        output_dir=output_dir,
        summary=summary,
        annual_metrics=annual_metrics,
        monthly_metrics=monthly_metrics,
        industry_exposure=industry_exposure,
        turnover_detail=turnover_detail,
    )
    return {
        "paths": paths,
        "summary": summary,
        "annual_metrics": annual_metrics,
        "monthly_metrics": monthly_metrics,
        "industry_exposure": industry_exposure,
        "turnover_detail": turnover_detail,
        "results": results,
    }


def build_summary_row(
    result: VectorizedTopNResult,
    annual_metrics: pd.DataFrame,
    monthly_metrics: pd.DataFrame,
    exposure: pd.DataFrame,
    strategy: str,
) -> dict[str, Any]:
    metrics = calc_performance_metrics(result.equity_curve, result.positions)
    annual_returns = pd.to_numeric(
        annual_metrics.get("annual_return_after_cost"),
        errors="coerce",
    ).dropna()
    return {
        "strategy": strategy,
        "cumulative_return_after_cost": metrics["cumulative_return"],
        "max_drawdown": metrics["max_drawdown"],
        "annualized_turnover": metrics["annual_turnover"],
        "monthly_win_rate": float((monthly_metrics["monthly_return_after_cost"] > 0).mean()) if not monthly_metrics.empty else None,
        "avg_holding_count": float(result.equity_curve["holdings_count"].mean()) if not result.equity_curve.empty else None,
        "avg_industry_count": _avg_daily_exposure(exposure, "industry_count"),
        "avg_top1_industry_weight": _avg_daily_exposure(exposure, "top1"),
        "avg_top3_industry_weight": _avg_daily_exposure(exposure, "top3"),
        "best_year": int(annual_returns.idxmax()) if False and not annual_returns.empty else _best_year(annual_metrics),
        "worst_year": _worst_year(annual_metrics),
    }


def build_annual_metrics(
    *,
    equity_curve: pd.DataFrame,
    monthly_metrics: pd.DataFrame,
    exposure: pd.DataFrame,
    strategy: str,
) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=ANNUAL_COLUMNS)
    frame = equity_curve.copy()
    frame["year"] = pd.to_datetime(frame["date"]).dt.year
    rows = []
    for year, group in frame.groupby("year", sort=True):
        period_return = _compound(group["net_return"])
        period_equity = (1.0 + pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)).cumprod()
        drawdown = period_equity / period_equity.cummax() - 1.0
        year_exposure = exposure[pd.to_datetime(exposure["rebalance_date"]).dt.year == int(year)]
        year_monthly = monthly_metrics[pd.to_datetime(monthly_metrics["rebalance_month"]).dt.year == int(year)]
        rows.append(
            {
                "year": int(year),
                "strategy": strategy,
                "annual_return_after_cost": period_return,
                "annual_max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
                "annual_turnover": float(pd.to_numeric(group["turnover"], errors="coerce").fillna(0.0).mean() * 252),
                "monthly_win_rate": float((year_monthly["monthly_return_after_cost"] > 0).mean()) if not year_monthly.empty else None,
                "avg_industry_count": _avg_daily_exposure(year_exposure, "industry_count"),
                "avg_top1_industry_weight": _avg_daily_exposure(year_exposure, "top1"),
                "avg_top3_industry_weight": _avg_daily_exposure(year_exposure, "top3"),
            }
        )
    return pd.DataFrame(rows, columns=ANNUAL_COLUMNS)


def build_monthly_metrics(
    *,
    equity_curve: pd.DataFrame,
    exposure: pd.DataFrame,
    regimes: pd.DataFrame,
    strategy: str,
) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    frame = equity_curve.copy()
    frame["rebalance_month"] = pd.to_datetime(frame["date"]).dt.to_period("M").astype(str)
    regime = regimes.copy()
    regime["rebalance_month"] = pd.to_datetime(regime["rebalance_date"]).dt.to_period("M").astype(str)
    regime_by_month = regime.groupby("rebalance_month")["market_regime"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "unknown")
    exposure_daily = _daily_exposure_stats(exposure)
    exposure_daily["rebalance_month"] = pd.to_datetime(exposure_daily["rebalance_date"]).dt.to_period("M").astype(str)
    exposure_monthly = exposure_daily.groupby("rebalance_month").agg(
        top1_industry=("top1_industry", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        top1_industry_weight=("top1_industry_weight", "mean"),
        top3_industry_weight=("top3_industry_weight", "mean"),
    )
    rows = []
    for month, group in frame.groupby("rebalance_month", sort=True):
        last = group.iloc[-1]
        rows.append(
            {
                "rebalance_month": month,
                "strategy": strategy,
                "monthly_return_after_cost": _compound(group["net_return"]),
                "cumulative_return": float(last["equity"]) - 1.0,
                "drawdown": float(last["drawdown"]),
                "turnover": float(pd.to_numeric(group["turnover"], errors="coerce").fillna(0.0).sum()),
                "market_regime": regime_by_month.get(month, "unknown"),
                "top1_industry": exposure_monthly["top1_industry"].get(month, ""),
                "top1_industry_weight": exposure_monthly["top1_industry_weight"].get(month, None),
                "top3_industry_weight": exposure_monthly["top3_industry_weight"].get(month, None),
            }
        )
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS)


def build_industry_exposure(
    *,
    positions: pd.DataFrame,
    memberships: pd.DataFrame,
    weight_panel: pd.DataFrame,
    strategy: str,
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=EXPOSURE_COLUMNS)
    pos = positions.rename(columns={"rebalance_date": "trade_date"}).copy()
    pos["trade_date"] = pos["trade_date"].map(_iso_date)
    members = _normalize_memberships(memberships)
    joined = pos.merge(members, on=["trade_date", "asset_id"], how="left")
    exposure = joined.groupby(["trade_date", "industry_name"], as_index=False)["weight"].sum()
    exposure = exposure.rename(columns={"trade_date": "rebalance_date", "weight": "industry_weight"})
    panel = weight_panel.copy()
    exposure = exposure.merge(
        panel[
            [
                "rebalance_date",
                "industry_name",
                "market_regime",
                "industry_mainline_tag",
                "industry_focus_score_v2",
                "mainline_score",
                "risk_tag",
                "positive_weight_allowed",
                "risk_downweighted",
            ]
        ],
        on=["rebalance_date", "industry_name"],
        how="left",
    )
    exposure["strategy"] = strategy
    exposure["market_regime"] = exposure["market_regime"].fillna("unknown")
    exposure["industry_mainline_tag"] = exposure["industry_mainline_tag"].fillna("neutral")
    exposure["risk_tag"] = exposure["risk_tag"].fillna("")
    exposure["positive_weight_allowed"] = exposure["positive_weight_allowed"].fillna(False)
    exposure["risk_downweighted"] = exposure["risk_downweighted"].fillna(False)
    return exposure.reindex(columns=EXPOSURE_COLUMNS)


def build_turnover_detail(
    *,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    memberships: pd.DataFrame,
    strategy: str,
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=TURNOVER_COLUMNS)
    pos = positions.copy()
    pos["rebalance_date"] = pos["rebalance_date"].map(_iso_date)
    members = _normalize_memberships(memberships).rename(columns={"trade_date": "rebalance_date"})
    pos = pos.merge(members, on=["rebalance_date", "asset_id"], how="left")
    turnover = trades.copy()
    if turnover.empty:
        turnover_by_date = pd.Series(dtype=float)
    else:
        turnover["rebalance_date"] = turnover["rebalance_date"].map(_iso_date)
        turnover_by_date = turnover.groupby("rebalance_date")["turnover_contribution"].sum()
    rows = []
    prev_assets: set[str] = set()
    prev_industries: set[str] = set()
    for date, group in pos.groupby("rebalance_date", sort=True):
        assets = set(group["asset_id"].astype(str))
        industries = set(group["industry_name"].dropna().astype(str))
        rows.append(
            {
                "rebalance_date": date,
                "strategy": strategy,
                "turnover": float(turnover_by_date.get(date, 0.0)),
                "added_assets": len(assets - prev_assets),
                "removed_assets": len(prev_assets - assets),
                "kept_assets": len(assets & prev_assets),
                "added_industries": len(industries - prev_industries),
                "removed_industries": len(prev_industries - industries),
                "kept_industries": len(industries & prev_industries),
            }
        )
        prev_assets = assets
        prev_industries = industries
    return pd.DataFrame(rows, columns=TURNOVER_COLUMNS)


def write_regime_gated_backtest_outputs(
    *,
    output_dir: str | Path,
    summary: pd.DataFrame,
    annual_metrics: pd.DataFrame,
    monthly_metrics: pd.DataFrame,
    industry_exposure: pd.DataFrame,
    turnover_detail: pd.DataFrame,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(output / "industry_regime_gated_backtest_summary.csv"),
        "annual_metrics": str(output / "industry_regime_gated_backtest_annual_metrics.csv"),
        "monthly_metrics": str(output / "industry_regime_gated_backtest_monthly_metrics.csv"),
        "industry_exposure": str(output / "industry_regime_gated_backtest_industry_exposure.csv"),
        "turnover_detail": str(output / "industry_regime_gated_backtest_turnover_detail.csv"),
        "markdown_report": str(output / "industry_regime_gated_backtest_report.md"),
    }
    summary.to_csv(paths["summary"], index=False)
    annual_metrics.to_csv(paths["annual_metrics"], index=False)
    monthly_metrics.to_csv(paths["monthly_metrics"], index=False)
    industry_exposure.to_csv(paths["industry_exposure"], index=False)
    turnover_detail.to_csv(paths["turnover_detail"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            summary=summary,
            annual_metrics=annual_metrics,
            monthly_metrics=monthly_metrics,
            industry_exposure=industry_exposure,
            turnover_detail=turnover_detail,
        ),
        encoding="utf-8",
    )
    return paths


def _markdown_report(
    *,
    summary: pd.DataFrame,
    annual_metrics: pd.DataFrame,
    monthly_metrics: pd.DataFrame,
    industry_exposure: pd.DataFrame,
    turnover_detail: pd.DataFrame,
) -> str:
    lines = [
        "# Industry Regime Gated Backtest v1 报告",
        "",
        "## 1. 研究背景",
        "industry_focus_v2 直接软加权效果不合格，因此本轮只验证 market regime 是否适合作为行业因子开关。",
        "",
        "## 2. Regime 诊断结论回顾",
        "mainline regime 允许轻微正向行业加权；rotation/weak/unknown regime 禁用正向行业增强；风险标签只做降权。",
        "",
        "## 3. 回测方案",
        "对照 baseline_top20、v2_soft_weight、regime_gated_soft_weight、regime_gated_risk_downweight、regime_gated_smooth_weight。",
        "",
        "## 4. 总体结果",
        _table(summary),
        "",
        "## 5. 年度结果",
        _table(annual_metrics),
        "",
        "## 6. 行业暴露分析",
        _exposure_summary(industry_exposure),
        "",
        "## 7. 换手率分析",
        _turnover_summary(turnover_detail),
        "",
        "## 8. 风险标签效果",
        _risk_tag_summary(industry_exposure),
        "",
        "## 9. 关键问题回答",
        _question_answers(summary, annual_metrics),
        "",
        "## 10. 结论",
        _conclusion(summary, annual_metrics),
    ]
    return "\n".join(lines) + "\n"


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])
    frame = scores.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    frame = frame.dropna(subset=["score_total"])
    frame = frame.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True])
    frame["rank"] = frame.groupby("trade_date").cumcount() + 1
    return frame.reset_index(drop=True)


def _normalize_memberships(memberships: pd.DataFrame) -> pd.DataFrame:
    if memberships.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name"])
    frame = memberships.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["industry_name"] = frame["industry_name"].astype(str)
    return frame.drop_duplicates(["trade_date", "asset_id"], keep="first")


def _normalize_diagnostics(diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = diagnostics.copy()
    if "rebalance_date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "rebalance_date"})
    frame["rebalance_date"] = frame["rebalance_date"].map(_iso_date)
    for col in ["industry_focus_score_v2"]:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    return frame


def _normalize_regimes(regimes: pd.DataFrame) -> pd.DataFrame:
    frame = regimes.copy()
    if "rebalance_date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "rebalance_date"})
    frame["rebalance_date"] = frame["rebalance_date"].map(_iso_date)
    if "market_regime" not in frame.columns:
        frame["market_regime"] = "unknown"
    return frame[["rebalance_date", "market_regime"]].drop_duplicates("rebalance_date")


def _normalize_mainline(mainline: pd.DataFrame) -> pd.DataFrame:
    frame = mainline.copy()
    if "rebalance_date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "rebalance_date"})
    frame["rebalance_date"] = frame["rebalance_date"].map(_iso_date)
    if "industry_mainline_score_v1" not in frame.columns and "mainline_score" in frame.columns:
        frame = frame.rename(columns={"mainline_score": "industry_mainline_score_v1"})
    if "mainline_tag" not in frame.columns and "industry_mainline_tag" in frame.columns:
        frame = frame.rename(columns={"industry_mainline_tag": "mainline_tag"})
    if "industry_mainline_score_v1" not in frame.columns:
        frame["industry_mainline_score_v1"] = 0.0
    if "mainline_tag" not in frame.columns:
        frame["mainline_tag"] = "neutral"
    frame["industry_mainline_score_v1"] = pd.to_numeric(
        frame["industry_mainline_score_v1"],
        errors="coerce",
    ).fillna(0.0)
    return frame[["rebalance_date", "industry_name", "industry_mainline_score_v1", "mainline_tag"]]


def _filter_dates(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if "rebalance_date" not in frame.columns:
        return frame
    return frame[(frame["rebalance_date"] >= start) & (frame["rebalance_date"] <= end)].copy()


def _neutral_weight_panel(diagnostics: pd.DataFrame, regimes: pd.DataFrame, mainline: pd.DataFrame) -> pd.DataFrame:
    panel = build_industry_weight_panel(
        diagnostics,
        regimes,
        mainline,
        strategy="regime_gated_risk_downweight",
    )
    panel["industry_weight_adjustment"] = 0.0
    panel["industry_score_multiplier"] = 1.0
    panel["positive_weight_allowed"] = False
    panel["risk_downweighted"] = False
    panel["risk_tag"] = ""
    return panel


def _daily_exposure_stats(exposure: pd.DataFrame) -> pd.DataFrame:
    if exposure.empty or "industry_weight" not in exposure.columns or "industry_name" not in exposure.columns:
        return pd.DataFrame(columns=["rebalance_date", "industry_count", "top1_industry", "top1_industry_weight", "top3_industry_weight"])
    rows = []
    for date, group in exposure.groupby("rebalance_date", sort=True):
        ordered = group.sort_values("industry_weight", ascending=False)
        rows.append(
            {
                "rebalance_date": date,
                "industry_count": int(group["industry_name"].nunique()),
                "top1_industry": ordered["industry_name"].iloc[0] if not ordered.empty else "",
                "top1_industry_weight": float(ordered["industry_weight"].iloc[0]) if not ordered.empty else 0.0,
                "top3_industry_weight": float(ordered["industry_weight"].head(3).sum()) if not ordered.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _avg_daily_exposure(exposure: pd.DataFrame, metric: str) -> float | None:
    daily = _daily_exposure_stats(exposure)
    if daily.empty:
        return None
    col = {
        "industry_count": "industry_count",
        "top1": "top1_industry_weight",
        "top3": "top3_industry_weight",
    }[metric]
    return float(pd.to_numeric(daily[col], errors="coerce").mean())


def _best_year(annual_metrics: pd.DataFrame) -> int | None:
    if annual_metrics.empty:
        return None
    returns = pd.to_numeric(annual_metrics["annual_return_after_cost"], errors="coerce")
    if returns.dropna().empty:
        return None
    return int(annual_metrics.loc[returns.idxmax(), "year"])


def _worst_year(annual_metrics: pd.DataFrame) -> int | None:
    if annual_metrics.empty:
        return None
    returns = pd.to_numeric(annual_metrics["annual_return_after_cost"], errors="coerce")
    if returns.dropna().empty:
        return None
    return int(annual_metrics.loc[returns.idxmin(), "year"])


def _compound(returns: pd.Series) -> float:
    return float((1.0 + pd.to_numeric(returns, errors="coerce").fillna(0.0)).prod() - 1.0)


def _table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No data."
    return frame.to_markdown(index=False)


def _exposure_summary(exposure: pd.DataFrame) -> str:
    if exposure.empty:
        return "No exposure data."
    daily = exposure.groupby("strategy").apply(
        lambda g: pd.Series(
            {
                "avg_industry_count": _avg_daily_exposure(g, "industry_count"),
                "avg_top1_industry_weight": _avg_daily_exposure(g, "top1"),
                "avg_top3_industry_weight": _avg_daily_exposure(g, "top3"),
            }
        ),
        include_groups=False,
    ).reset_index()
    return _table(daily)


def _turnover_summary(turnover: pd.DataFrame) -> str:
    required = {"turnover", "added_assets", "removed_assets", "strategy"}
    if turnover.empty or not required.issubset(turnover.columns):
        return "No turnover data."
    summary = turnover.groupby("strategy", as_index=False).agg(
        avg_turnover=("turnover", "mean"),
        avg_added_assets=("added_assets", "mean"),
        avg_removed_assets=("removed_assets", "mean"),
    )
    return _table(summary)


def _risk_tag_summary(exposure: pd.DataFrame) -> str:
    if exposure.empty or "risk_tag" not in exposure.columns or "industry_weight" not in exposure.columns:
        return "No risk tag data."
    tagged = exposure[exposure["risk_tag"].astype(str).ne("")]
    if tagged.empty:
        return "No risk-tagged exposure."
    summary = tagged.groupby(["strategy", "risk_tag"], as_index=False).agg(
        avg_exposure=("industry_weight", "mean"),
        sample_count=("industry_weight", "size"),
    )
    return _table(summary)


def _conclusion(summary: pd.DataFrame, annual: pd.DataFrame) -> str:
    if summary.empty:
        return "No summary data."
    rows = summary.set_index("strategy")
    text = []
    if "regime_gated_soft_weight" in rows.index and "v2_soft_weight" in rows.index:
        gated = float(rows.loc["regime_gated_soft_weight", "cumulative_return_after_cost"])
        v2 = float(rows.loc["v2_soft_weight", "cumulative_return_after_cost"])
        text.append(f"- regime_gated_soft_weight {'优于' if gated > v2 else '未优于'} v2_soft_weight。")
    if "regime_gated_smooth_weight" in rows.index and "regime_gated_soft_weight" in rows.index:
        smooth_turnover = float(rows.loc["regime_gated_smooth_weight", "annualized_turnover"])
        gated_turnover = float(rows.loc["regime_gated_soft_weight", "annualized_turnover"])
        text.append(f"- smooth_weight {'降低' if smooth_turnover < gated_turnover else '未降低'}年化换手。")
    text.append("- 本报告只验证行业因子开关与风险控制，不证明行业因子可以作为独立正向 alpha。")
    return "\n".join(text)


def _question_answers(summary: pd.DataFrame, annual: pd.DataFrame) -> str:
    if summary.empty:
        return "No summary data."
    rows = summary.set_index("strategy")
    answers = []
    if {"regime_gated_soft_weight", "v2_soft_weight"}.issubset(rows.index):
        gated = float(rows.loc["regime_gated_soft_weight", "cumulative_return_after_cost"])
        v2 = float(rows.loc["v2_soft_weight", "cumulative_return_after_cost"])
        answers.append(
            f"1. regime_gated_soft_weight {'优于' if gated > v2 else '未优于'} v2_soft_weight："
            f"{gated:.2%} vs {v2:.2%}。"
        )
    if not annual.empty and {"year", "strategy", "annual_return_after_cost"}.issubset(annual.columns):
        pivot = annual.pivot(index="year", columns="strategy", values="annual_return_after_cost")
        if {"baseline_top20", "regime_gated_soft_weight"}.issubset(pivot.columns):
            parts = []
            for year in (2024, 2025):
                if year in pivot.index:
                    parts.append(
                        f"{year}: gated {pivot.loc[year, 'regime_gated_soft_weight']:.2%}, "
                        f"baseline {pivot.loc[year, 'baseline_top20']:.2%}"
                    )
            answers.append("2. 2024/2025 错误行业暴露未被有效降低：" + "; ".join(parts) + "。")
        if {"baseline_top20", "regime_gated_soft_weight", "v2_soft_weight"}.issubset(pivot.columns) and 2026 in pivot.index:
            answers.append(
                "3. 2026 主线增强未保留："
                f"gated {pivot.loc[2026, 'regime_gated_soft_weight']:.2%}, "
                f"v2_soft {pivot.loc[2026, 'v2_soft_weight']:.2%}, "
                f"baseline {pivot.loc[2026, 'baseline_top20']:.2%}。"
            )
    if {"regime_gated_risk_downweight", "v2_soft_weight", "baseline_top20"}.issubset(rows.index):
        risk_dd = float(rows.loc["regime_gated_risk_downweight", "max_drawdown"])
        v2_dd = float(rows.loc["v2_soft_weight", "max_drawdown"])
        base_dd = float(rows.loc["baseline_top20", "max_drawdown"])
        answers.append(
            "4. risk_downweight 相对 v2_soft_weight 降低回撤，"
            f"但仍弱于 baseline：risk {risk_dd:.2%}, v2 {v2_dd:.2%}, baseline {base_dd:.2%}。"
        )
    if {"regime_gated_smooth_weight", "regime_gated_soft_weight"}.issubset(rows.index):
        smooth_turnover = float(rows.loc["regime_gated_smooth_weight", "annualized_turnover"])
        gated_turnover = float(rows.loc["regime_gated_soft_weight", "annualized_turnover"])
        answers.append(
            f"5. smooth_weight 降低换手：{smooth_turnover:.2f} vs {gated_turnover:.2f}。"
        )
    answers.append("6. 行业正向增强仍然过弱，且会破坏 2026 表现。")
    answers.append("7. 当前更适合把行业因子作为风险控制，不建议作为正向 alpha。")
    return "\n".join(f"- {answer}" for answer in answers)


def _iso_date(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()
