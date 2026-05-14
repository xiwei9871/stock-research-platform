from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.industry_focus_v2 import load_research_inputs
from stock_research.industry_regime_gated_backtest import (
    _avg_daily_exposure,
    _best_year,
    _compound,
    _daily_exposure_stats,
    _filter_dates,
    _iso_date,
    _normalize_memberships,
    _normalize_scores,
    _table,
    _worst_year,
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
    "industry_cap_top20",
    "top3_industry_cap_top20",
    "risk_tag_light_downweight",
    "exposure_cap_plus_risk_downweight",
    "exposure_cap_plus_turnover_smooth",
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
    "top1_industry",
    "top1_industry_weight",
    "top3_industry_weight",
]

EXPOSURE_COLUMNS = [
    "rebalance_date",
    "strategy",
    "industry_name",
    "industry_weight",
    "industry_mainline_tag",
    "risk_tag",
    "exposure_capped",
    "risk_downweighted",
    "final_industry_weight",
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


def select_exposure_capped_topn(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    *,
    top_n: int = 20,
    max_industry_count: int | None = None,
    max_top3_count: int | None = None,
    smooth_turnover: bool = False,
    keep_candidate_rank: int = 60,
) -> pd.DataFrame:
    score_frame = _normalize_scores(scores)
    members = _normalize_memberships(memberships)
    joined = score_frame.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    ).sort_values(["trade_date", "rank", "score_total", "asset_id"], ascending=[True, True, False, True])

    selected_rows: list[dict[str, Any]] = []
    previous_assets: set[str] = set()
    effective_industry_cap = max_industry_count
    if max_top3_count is not None:
        top3_implied_cap = max(1, int(max_top3_count // 3))
        effective_industry_cap = (
            min(effective_industry_cap, top3_implied_cap)
            if effective_industry_cap is not None
            else top3_implied_cap
        )

    for trade_date, group in joined.groupby("trade_date", sort=True):
        ordered = group.sort_values(["rank", "score_total", "asset_id"], ascending=[True, False, True])
        chosen: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        if smooth_turnover and previous_assets:
            keep_pool = ordered[ordered["rank"] <= keep_candidate_rank]
            keep_pool = keep_pool[keep_pool["asset_id"].astype(str).isin(previous_assets)]
            for row in keep_pool.to_dict("records"):
                if len(chosen) >= top_n:
                    break
                if _can_add_industry(
                    counts,
                    str(row["industry_name"]),
                    effective_industry_cap,
                    max_top3_count,
                ):
                    chosen.append(row)
                    counts[str(row["industry_name"])] = counts.get(str(row["industry_name"]), 0) + 1

        chosen_assets = {str(row["asset_id"]) for row in chosen}
        for row in ordered.to_dict("records"):
            if len(chosen) >= top_n:
                break
            if str(row["asset_id"]) in chosen_assets:
                continue
            industry = str(row["industry_name"])
            if not _can_add_industry(counts, industry, effective_industry_cap, max_top3_count):
                continue
            chosen.append(row)
            chosen_assets.add(str(row["asset_id"]))
            counts[industry] = counts.get(industry, 0) + 1

        if len(chosen) < top_n:
            for row in ordered.to_dict("records"):
                if len(chosen) >= top_n:
                    break
                if str(row["asset_id"]) in chosen_assets:
                    continue
                chosen.append(row)
                chosen_assets.add(str(row["asset_id"]))

        for rank, row in enumerate(chosen[:top_n], start=1):
            selected_rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": str(row["asset_id"]),
                    "rank": rank,
                    "score_total": float(row["score_total"]),
                }
            )
        previous_assets = {str(row["asset_id"]) for row in chosen[:top_n]}
    return pd.DataFrame(selected_rows, columns=["trade_date", "asset_id", "rank", "score_total"])


def count_kept_assets(selected_scores: pd.DataFrame, trade_date: str) -> int:
    frame = _normalize_scores(selected_scores)
    dates = sorted(frame["trade_date"].unique())
    if trade_date not in dates:
        return 0
    index = dates.index(trade_date)
    if index == 0:
        return 0
    previous = set(frame[frame["trade_date"] == dates[index - 1]]["asset_id"].astype(str))
    current = set(frame[frame["trade_date"] == trade_date]["asset_id"].astype(str))
    return len(previous & current)


def apply_risk_tag_light_downweight(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    mainline: pd.DataFrame,
    *,
    risk_multiplier: float = 0.90,
) -> pd.DataFrame:
    score_frame = _normalize_scores(scores)
    members = _normalize_memberships(memberships)
    risk = _risk_panel(mainline)
    joined = score_frame.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    joined = joined.merge(
        risk.rename(columns={"rebalance_date": "trade_date"}),
        on=["trade_date", "industry_name"],
        how="left",
    )
    joined["risk_tag"] = joined["risk_tag"].fillna("")
    joined["industry_risk_multiplier"] = joined["risk_tag"].ne("").map(
        {True: float(risk_multiplier), False: 1.0}
    )
    original = pd.to_numeric(joined["score_total"], errors="coerce").fillna(0.0)
    multiplier = pd.to_numeric(joined["industry_risk_multiplier"], errors="coerce").fillna(1.0)
    joined["score_total"] = original.where(original < 0, original * multiplier)
    joined.loc[original < 0, "score_total"] = original[original < 0] / multiplier[original < 0]
    return _normalize_scores(
        joined[["trade_date", "asset_id", "score_total", "industry_risk_multiplier"]]
    )


def build_exposure_cap_plus_risk_downweight_scores(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    mainline: pd.DataFrame,
    *,
    diagnostics: pd.DataFrame | None = None,
    top_n: int = 20,
    max_industry_count: int | None = None,
    max_top3_count: int | None = None,
    risk_multiplier: float = 0.90,
) -> pd.DataFrame:
    del diagnostics
    adjusted = apply_risk_tag_light_downweight(
        scores,
        memberships,
        mainline,
        risk_multiplier=risk_multiplier,
    )
    return select_exposure_capped_topn(
        adjusted,
        memberships,
        top_n=top_n,
        max_industry_count=max_industry_count,
        max_top3_count=max_top3_count,
    )


def run_industry_exposure_risk_control(
    *,
    start_date: object,
    end_date: object,
    diagnostics_path: str | Path,
    regime_path: str | Path,
    mainline_path: str | Path,
    output_dir: str | Path = Path("/Users/xiwei/stock_research/outputs/research"),
    top_n: int = 20,
    transaction_cost_bps: float = 20.0,
    industry_cap: float = 0.25,
    top3_industry_cap: float = 0.60,
    risk_multiplier: float = 0.90,
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    diagnostics = _filter_dates(_normalize_optional_dates(pd.read_csv(diagnostics_path)), start, end)
    _ = _filter_dates(_normalize_optional_dates(pd.read_csv(regime_path)), start, end)
    mainline = _filter_dates(_normalize_mainline(pd.read_csv(mainline_path)), start, end)
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
    industry_count_cap = max(1, int(top_n * industry_cap))
    top3_count_cap = max(1, int(top_n * top3_industry_cap))

    strategy_scores = {
        "baseline_top20": scores,
        "industry_cap_top20": select_exposure_capped_topn(
            scores,
            memberships,
            top_n=top_n,
            max_industry_count=industry_count_cap,
        ),
        "top3_industry_cap_top20": select_exposure_capped_topn(
            scores,
            memberships,
            top_n=top_n,
            max_top3_count=top3_count_cap,
        ),
        "risk_tag_light_downweight": apply_risk_tag_light_downweight(
            scores,
            memberships,
            mainline,
            risk_multiplier=risk_multiplier,
        ),
        "exposure_cap_plus_risk_downweight": build_exposure_cap_plus_risk_downweight_scores(
            scores,
            memberships,
            mainline,
            diagnostics=diagnostics,
            top_n=top_n,
            max_industry_count=industry_count_cap,
            max_top3_count=top3_count_cap,
            risk_multiplier=risk_multiplier,
        ),
        "exposure_cap_plus_turnover_smooth": select_exposure_capped_topn(
            scores,
            memberships,
            top_n=top_n,
            max_industry_count=industry_count_cap,
            max_top3_count=top3_count_cap,
            smooth_turnover=True,
            keep_candidate_rank=max(top_n * 3, 60),
        ),
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
        exposure = build_industry_exposure(
            positions=result.positions,
            memberships=memberships,
            mainline=mainline,
            strategy=strategy,
            exposure_capped=strategy
            in {
                "industry_cap_top20",
                "top3_industry_cap_top20",
                "exposure_cap_plus_risk_downweight",
                "exposure_cap_plus_turnover_smooth",
            },
            risk_downweight_enabled=strategy
            in {"risk_tag_light_downweight", "exposure_cap_plus_risk_downweight"},
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
    paths = write_exposure_risk_control_outputs(
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
        "best_year": _best_year(annual_metrics),
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
    strategy: str,
) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    frame = equity_curve.copy()
    frame["rebalance_month"] = pd.to_datetime(frame["date"]).dt.to_period("M").astype(str)
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
    mainline: pd.DataFrame,
    strategy: str,
    exposure_capped: bool,
    risk_downweight_enabled: bool,
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=EXPOSURE_COLUMNS)
    pos = positions.rename(columns={"rebalance_date": "trade_date"}).copy()
    pos["trade_date"] = pos["trade_date"].map(_iso_date)
    members = _normalize_memberships(memberships)
    joined = pos.merge(members, on=["trade_date", "asset_id"], how="left")
    exposure = joined.groupby(["trade_date", "industry_name"], as_index=False)["weight"].sum()
    exposure = exposure.rename(columns={"trade_date": "rebalance_date", "weight": "industry_weight"})
    risk = _risk_panel(mainline)
    exposure = exposure.merge(risk, on=["rebalance_date", "industry_name"], how="left")
    exposure["strategy"] = strategy
    exposure["industry_mainline_tag"] = exposure["industry_mainline_tag"].fillna("neutral")
    exposure["risk_tag"] = exposure["risk_tag"].fillna("")
    exposure["exposure_capped"] = bool(exposure_capped)
    exposure["risk_downweighted"] = risk_downweight_enabled & exposure["risk_tag"].ne("")
    exposure["final_industry_weight"] = exposure["industry_weight"]
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
    if trades.empty:
        turnover_by_date = pd.Series(dtype=float)
    else:
        turnover = trades.copy()
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


def write_exposure_risk_control_outputs(
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
        "summary": str(output / "industry_exposure_risk_control_summary.csv"),
        "annual_metrics": str(output / "industry_exposure_risk_control_annual_metrics.csv"),
        "monthly_metrics": str(output / "industry_exposure_risk_control_monthly_metrics.csv"),
        "industry_exposure": str(output / "industry_exposure_risk_control_industry_exposure.csv"),
        "turnover_detail": str(output / "industry_exposure_risk_control_turnover_detail.csv"),
        "markdown_report": str(output / "industry_exposure_risk_control_report.md"),
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


def _can_add_industry(
    counts: dict[str, int],
    industry: str,
    max_industry_count: int | None,
    max_top3_count: int | None,
) -> bool:
    projected = counts.copy()
    projected[industry] = projected.get(industry, 0) + 1
    if max_industry_count is not None and projected[industry] > max_industry_count:
        return False
    if max_top3_count is not None:
        top3 = sum(sorted(projected.values(), reverse=True)[:3])
        if top3 > max_top3_count:
            return False
    return True


def _risk_panel(mainline: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_mainline(mainline)
    frame = frame.rename(columns={"mainline_tag": "industry_mainline_tag"})
    frame["risk_tag"] = frame["industry_mainline_tag"].where(frame["industry_mainline_tag"].isin(RISK_TAGS), "")
    return frame[["rebalance_date", "industry_name", "industry_mainline_tag", "risk_tag"]]


def _normalize_mainline(mainline: pd.DataFrame) -> pd.DataFrame:
    frame = mainline.copy()
    if "rebalance_date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "rebalance_date"})
    frame["rebalance_date"] = frame["rebalance_date"].map(_iso_date)
    if "mainline_tag" not in frame.columns and "industry_mainline_tag" in frame.columns:
        frame = frame.rename(columns={"industry_mainline_tag": "mainline_tag"})
    if "industry_mainline_score_v1" not in frame.columns:
        frame["industry_mainline_score_v1"] = 0.0
    if "mainline_tag" not in frame.columns:
        frame["mainline_tag"] = "neutral"
    return frame[["rebalance_date", "industry_name", "industry_mainline_score_v1", "mainline_tag"]].drop_duplicates(
        ["rebalance_date", "industry_name"],
        keep="first",
    )


def _normalize_optional_dates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    if "rebalance_date" not in result.columns and "trade_date" in result.columns:
        result = result.rename(columns={"trade_date": "rebalance_date"})
    if "rebalance_date" in result.columns:
        result["rebalance_date"] = result["rebalance_date"].map(_iso_date)
    return result


def _markdown_report(
    *,
    summary: pd.DataFrame,
    annual_metrics: pd.DataFrame,
    monthly_metrics: pd.DataFrame,
    industry_exposure: pd.DataFrame,
    turnover_detail: pd.DataFrame,
) -> str:
    lines = [
        "# Industry Exposure Risk Control v1 报告",
        "",
        "## 1. 研究背景",
        "industry_focus_v2 和 regime_gated_backtest 已证明行业正向 alpha 不合格。本轮只验证行业暴露约束、风险标签轻度降权和换手平滑是否能作为风险控制层。",
        "",
        "## 2. 策略设计",
        "对照 baseline_top20、industry_cap_top20、top3_industry_cap_top20、risk_tag_light_downweight、exposure_cap_plus_risk_downweight、exposure_cap_plus_turnover_smooth。所有策略都不做行业正向加权。",
        "",
        "## 3. 总体结果",
        _table(summary),
        "",
        "## 4. 年度结果",
        _table(annual_metrics),
        "",
        "## 5. 行业暴露变化",
        _exposure_summary(industry_exposure),
        "",
        "## 6. 回撤与风险控制",
        _drawdown_summary(summary),
        "",
        "## 7. 换手率分析",
        _turnover_summary(turnover_detail),
        "",
        "## 8. 结论",
        _question_answers(summary, annual_metrics),
    ]
    return "\n".join(lines) + "\n"


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


def _drawdown_summary(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "No summary data."
    cols = ["strategy", "cumulative_return_after_cost", "max_drawdown"]
    return _table(summary[[col for col in cols if col in summary.columns]])


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


def _question_answers(summary: pd.DataFrame, annual: pd.DataFrame) -> str:
    if summary.empty:
        return "No summary data."
    rows = summary.set_index("strategy")
    answers = []
    baseline_return = _metric(rows, "baseline_top20", "cumulative_return_after_cost")
    baseline_dd = _metric(rows, "baseline_top20", "max_drawdown")
    for strategy in [
        "industry_cap_top20",
        "top3_industry_cap_top20",
        "risk_tag_light_downweight",
        "exposure_cap_plus_risk_downweight",
        "exposure_cap_plus_turnover_smooth",
    ]:
        if strategy in rows.index:
            ret = _metric(rows, strategy, "cumulative_return_after_cost")
            dd = _metric(rows, strategy, "max_drawdown")
            turnover = _metric(rows, strategy, "annualized_turnover")
            answers.append(
                f"- {strategy}: 收益 {ret:.2%}, 最大回撤 {dd:.2%}, 年化换手 {turnover:.2f}; "
                f"相对 baseline 收益差 {ret - baseline_return:.2%}, 回撤差 {dd - baseline_dd:.2%}。"
            )
    if {"industry_cap_top20", "top3_industry_cap_top20"}.issubset(rows.index):
        cap_dd = _metric(rows, "industry_cap_top20", "max_drawdown")
        top3_dd = _metric(rows, "top3_industry_cap_top20", "max_drawdown")
        answers.append(f"- Top3 合计约束{'更' if top3_dd > cap_dd else '未更'}有效降低回撤：{top3_dd:.2%} vs {cap_dd:.2%}。")
    if {"exposure_cap_plus_turnover_smooth", "industry_cap_top20"}.issubset(rows.index):
        smooth_turnover = _metric(rows, "exposure_cap_plus_turnover_smooth", "annualized_turnover")
        cap_turnover = _metric(rows, "industry_cap_top20", "annualized_turnover")
        answers.append(f"- turnover_smooth {'降低' if smooth_turnover < cap_turnover else '未降低'}换手：{smooth_turnover:.2f} vs {cap_turnover:.2f}。")
    if annual.empty:
        answers.append("- 年度数据为空，无法判断 2024/2025/2026 是否恶化。")
    else:
        answers.append("- 行业模块仍不作为 alpha 层；若保留，应仅作为风险控制和暴露解释层。")
        answers.append("- 下一步更应把研究重心转向 Dragon Strategy、分时数据和龙虎榜，而不是继续调行业正向 alpha。")
    return "\n".join(answers)


def _metric(rows: pd.DataFrame, strategy: str, column: str) -> float:
    if strategy not in rows.index or column not in rows.columns:
        return 0.0
    value = rows.loc[strategy, column]
    if pd.isna(value):
        return 0.0
    return float(value)
