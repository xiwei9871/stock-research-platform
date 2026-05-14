from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.performance_metrics import calc_performance_metrics
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
    run_vectorized_topn_backtest,
)


FIXED_FOCUS_INDUSTRIES = (
    "计算机、通信和其他电子设备制造业",
    "专用设备制造业",
    "软件和信息技术服务业",
)

FOCUS_COLUMNS = [
    "trade_date",
    "industry_name",
    "selection_mode",
    "focus_rank",
    "industry_focus_score",
]

INDUSTRY_SCORE_COLUMNS = [
    "trade_date",
    "industry_name",
    "stock_count",
    "industry_ret_20d",
    "industry_ret_60d",
    "industry_excess_ret_20d",
    "industry_excess_ret_60d",
    "industry_amount_ratio_5_20",
    "industry_amount_ratio_20_60",
    "stock_amount_expansion_ratio",
    "up_ratio_20d",
    "above_ma20_ratio",
    "above_ma60_ratio",
    "new_high_60d_ratio",
    "top100_count",
    "top100_overweight_ratio",
    "top_decile_score_mean",
    "industry_trend_r2_20",
    "near_high_score",
    "volatility_20d",
    "max_drawdown_20d",
    "ret_5d",
    "one_day_return_abs",
    "momentum_score",
    "breadth_score",
    "volume_score",
    "candidate_density_score",
    "quality_score",
    "overheat_penalty",
    "industry_focus_score",
]

SUMMARY_COLUMNS = [
    "variant",
    "transaction_cost_bps",
    "score_rows",
    "position_rows",
    "trade_rows",
    "cumulative_return",
    "annual_return",
    "annual_volatility",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "win_rate",
    "average_holding_days",
    "annual_turnover",
    "periods",
]


@dataclass(frozen=True)
class IndustryFocusConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    dynamic_top_k: int = 4
    enter_top_n: int = 4
    exit_top_n: int = 8
    max_focus_industries: int = 6
    min_focus_industries: int = 2
    min_industry_stocks: int = 20
    transaction_cost_bps: tuple[float, ...] = (0.0, 20.0)
    industry_system: str = "csrc"
    industry_level: int = 1
    adjust_type: str = "hfq"


def rank_by_date(
    frame: pd.DataFrame,
    *,
    value_col: str,
    output_col: str,
    ascending: bool = True,
) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        result[output_col] = pd.Series(dtype="float64")
        return result
    result["trade_date"] = result["trade_date"].map(_iso_date)
    result[value_col] = pd.to_numeric(result[value_col], errors="coerce")
    result[output_col] = result.groupby("trade_date", group_keys=False)[value_col].rank(
        method="average",
        pct=True,
        ascending=ascending,
    )
    return result


def build_industry_scores(
    *,
    prices: pd.DataFrame,
    memberships: pd.DataFrame,
    stock_scores: pd.DataFrame,
    min_industry_stocks: int = 20,
    top_candidate_count: int = 100,
    short_window: int = 20,
    long_window: int = 60,
) -> pd.DataFrame:
    merged = _merge_price_membership(prices, memberships)
    if merged.empty:
        return pd.DataFrame(columns=INDUSTRY_SCORE_COLUMNS)

    enriched = _add_stock_history_metrics(
        merged,
        short_window=short_window,
        long_window=long_window,
    )
    industry_daily = _aggregate_industry_daily(
        enriched,
        min_industry_stocks=min_industry_stocks,
        short_window=short_window,
        long_window=long_window,
    )
    if industry_daily.empty:
        return pd.DataFrame(columns=INDUSTRY_SCORE_COLUMNS)

    candidate_metrics = _candidate_density_metrics(
        stock_scores=stock_scores,
        memberships=memberships,
        min_industry_stocks=min_industry_stocks,
        top_candidate_count=top_candidate_count,
    )
    frame = industry_daily.merge(candidate_metrics, on=["trade_date", "industry_name"], how="left")
    for col in ["top100_count", "top100_overweight_ratio", "top_decile_score_mean"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    scored = _build_composite_scores(frame)
    return scored.reindex(columns=INDUSTRY_SCORE_COLUMNS)


def select_dynamic_topk_focus(
    industry_scores: pd.DataFrame,
    *,
    top_k: int = 4,
    min_score_percentile: float | None = None,
) -> pd.DataFrame:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    scores = _normalize_industry_scores(industry_scores)
    if scores.empty:
        return _empty_focus_frame()
    ranked = _add_rank_number(scores)
    selected = ranked[ranked["focus_rank"] <= int(top_k)].copy()
    if min_score_percentile is not None:
        selected = selected[selected["score_percentile"] >= float(min_score_percentile)]
    selected["selection_mode"] = "dynamic_topk"
    return selected[FOCUS_COLUMNS].reset_index(drop=True)


def select_dynamic_hysteresis_focus(
    industry_scores: pd.DataFrame,
    *,
    enter_top_n: int = 4,
    exit_top_n: int = 8,
    max_focus_industries: int = 6,
    min_focus_industries: int = 2,
) -> pd.DataFrame:
    if enter_top_n <= 0 or exit_top_n <= 0:
        raise ValueError("enter_top_n and exit_top_n must be positive")
    scores = _add_rank_number(_normalize_industry_scores(industry_scores))
    if scores.empty:
        return _empty_focus_frame()

    rows: list[dict[str, Any]] = []
    active: set[str] = set()
    for trade_date, day in scores.groupby("trade_date", sort=True):
        ordered = day.sort_values(["focus_rank", "industry_name"]).copy()
        rank_map = dict(zip(ordered["industry_name"], ordered["focus_rank"], strict=False))
        active = {name for name in active if rank_map.get(name, 999999) <= int(exit_top_n)}
        active.update(ordered[ordered["focus_rank"] <= int(enter_top_n)]["industry_name"].tolist())
        if len(active) < int(min_focus_industries):
            active.update(ordered.head(int(min_focus_industries))["industry_name"].tolist())
        selected_names = [
            name
            for name in ordered["industry_name"].tolist()
            if name in active
        ][: int(max_focus_industries)]
        active = set(selected_names)
        for name in selected_names:
            row = ordered[ordered["industry_name"] == name].iloc[0]
            rows.append(
                {
                    "trade_date": trade_date,
                    "industry_name": name,
                    "selection_mode": "dynamic_hysteresis",
                    "focus_rank": int(row["focus_rank"]),
                    "industry_focus_score": float(row["industry_focus_score"]),
                }
            )
    return pd.DataFrame(rows, columns=FOCUS_COLUMNS)


def select_fixed_focus(
    *,
    trade_dates: list[str] | tuple[str, ...],
    focus_industries: tuple[str, ...] = FIXED_FOCUS_INDUSTRIES,
) -> pd.DataFrame:
    rows = [
        {
            "trade_date": _iso_date(trade_date),
            "industry_name": industry_name,
            "selection_mode": "fixed_ex_post",
            "focus_rank": pd.NA,
            "industry_focus_score": pd.NA,
        }
        for trade_date in sorted({_iso_date(date) for date in trade_dates})
        for industry_name in focus_industries
    ]
    return pd.DataFrame(rows, columns=FOCUS_COLUMNS)


def filter_scores_to_focus_industries(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    focus_industries: pd.DataFrame,
) -> pd.DataFrame:
    score_frame = _normalize_scores(scores)
    member_frame = _normalize_memberships(memberships)
    focus_frame = focus_industries.copy()
    if score_frame.empty or member_frame.empty or focus_frame.empty:
        return pd.DataFrame(columns=[*score_frame.columns, "industry_name"])
    focus_frame["trade_date"] = focus_frame["trade_date"].map(_iso_date)
    focus_frame["industry_name"] = focus_frame["industry_name"].astype(str)
    joined = score_frame.merge(
        member_frame[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    allowed = focus_frame[["trade_date", "industry_name"]].drop_duplicates()
    filtered = joined.merge(allowed, on=["trade_date", "industry_name"], how="inner")
    filtered = filtered.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).copy()
    filtered["rank"] = filtered.groupby("trade_date").cumcount() + 1
    return filtered.reset_index(drop=True)


def summarize_variant_result(
    *,
    variant: str,
    transaction_cost_bps: float,
    score_rows: int,
    result_summary: dict[str, Any],
    position_rows: int = 0,
    trade_rows: int = 0,
) -> dict[str, Any]:
    row = {
        "variant": variant,
        "transaction_cost_bps": float(transaction_cost_bps),
        "score_rows": int(score_rows),
        "position_rows": int(position_rows),
        "trade_rows": int(trade_rows),
    }
    row.update(result_summary)
    return row


def run_industry_focus_backtest_report(
    *,
    start_date: object,
    end_date: object,
    top_n: int = 20,
    dynamic_top_k: int = 4,
    min_industry_stocks: int = 20,
    transaction_cost_bps: tuple[float, ...] = (0.0, 20.0),
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    lookback_start = (pd.Timestamp(start) - pd.Timedelta(days=120)).date().isoformat()
    stock_scores = load_stock_scores(start_date=start, end_date=end, service=service)
    prices = load_prices(
        start_date=lookback_start,
        end_date=end,
        adjust_type=adjust_type,
        service=service,
    )
    memberships = load_industry_memberships(
        start_date=lookback_start,
        end_date=end,
        industry_system=industry_system,
        industry_level=industry_level,
        service=service,
    )

    industry_scores = build_industry_scores(
        prices=prices,
        memberships=memberships,
        stock_scores=stock_scores,
        min_industry_stocks=min_industry_stocks,
    )
    industry_scores = industry_scores[
        (industry_scores["trade_date"] >= start) & (industry_scores["trade_date"] <= end)
    ].reset_index(drop=True)
    trade_dates = sorted(stock_scores["trade_date"].astype(str).unique().tolist())
    focus_frames = {
        "fixed_focus_pool_top20": select_fixed_focus(trade_dates=trade_dates),
        "dynamic_topk_focus_pool_top20": select_dynamic_topk_focus(
            industry_scores,
            top_k=dynamic_top_k,
        ),
        "dynamic_hysteresis_focus_pool_top20": select_dynamic_hysteresis_focus(
            industry_scores,
        ),
    }

    variant_scores = {"base_top20": _normalize_scores(stock_scores)}
    for variant, focus in focus_frames.items():
        variant_scores[variant] = filter_scores_to_focus_industries(stock_scores, memberships, focus)

    results: list[tuple[str, float, VectorizedTopNResult]] = []
    summary_rows: list[dict[str, Any]] = []
    price_inputs = prices[["trade_date", "asset_id", "close"]].copy()
    for variant, scores in variant_scores.items():
        for cost in transaction_cost_bps:
            config = VectorizedTopNConfig(
                start_date=start,
                end_date=end,
                top_n=top_n,
                rebalance_frequency="daily",
                transaction_cost_bps=float(cost),
            )
            result = run_vectorized_topn_backtest(scores, price_inputs, config)
            results.append((variant, float(cost), result))
            summary_rows.append(
                summarize_variant_result(
                    variant=variant,
                    transaction_cost_bps=float(cost),
                    score_rows=len(scores),
                    position_rows=len(result.positions),
                    trade_rows=len(result.trades),
                    result_summary=calc_performance_metrics(result.equity_curve, result.positions),
                )
            )

    summary = pd.DataFrame(summary_rows).reindex(columns=SUMMARY_COLUMNS)
    focus_daily = (
        pd.concat(focus_frames.values(), ignore_index=True)
        if focus_frames
        else _empty_focus_frame()
    )
    top100_industry_daily = _top100_industry_daily(stock_scores, memberships)
    coverage = _focus_coverage_by_variant(stock_scores, memberships, focus_frames)
    monthly_returns = _monthly_returns(results)
    output_dir = Path(reports_dir) / f"industry_focus_score_v1_{start.replace('-', '')}_{end.replace('-', '')}"
    paths = write_industry_focus_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_scores=industry_scores,
        focus_industries_daily=focus_daily,
        top100_industry_daily=top100_industry_daily,
        summary=summary,
        monthly_returns=monthly_returns,
        focus_coverage=coverage,
        results=results,
    )
    return {
        "paths": paths,
        "summary": summary,
        "industry_scores": industry_scores,
        "focus_industries_daily": focus_daily,
        "top100_industry_daily": top100_industry_daily,
        "monthly_returns": monthly_returns,
        "focus_coverage": coverage,
    }


def load_stock_scores(
    *,
    start_date: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    config = manual_v1_config()
    rows: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _month_chunks(start_date, end_date):
        chunk = _load_stock_scores_sql(
            start_date=chunk_start,
            end_date=chunk_end,
            calc_version=config["calc_version"],
            factor_directions=config["factor_directions"],
            weights=config["weights"],
            service=service,
        )
        if not chunk.empty:
            rows.append(chunk)
        print(
            f"industry_focus_score|stock_score_chunk|{chunk_start}|{chunk_end}|rows|{len(chunk)}",
            file=sys.stderr,
            flush=True,
        )
    if not rows:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])
    return _normalize_scores(pd.concat(rows, ignore_index=True))


def _load_stock_scores_sql(
    *,
    start_date: str,
    end_date: str,
    calc_version: str,
    factor_directions: dict[str, str],
    weights: dict[str, float],
    service: str,
) -> pd.DataFrame:
    weighted_factors = []
    for score_col, raw_weight in weights.items():
        factor_name = score_col.removesuffix("_score")
        direction = factor_directions.get(factor_name)
        if direction not in {"higher", "lower"}:
            continue
        weighted_factors.append((factor_name, direction, float(raw_weight)))
    if not weighted_factors:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])

    values_sql = ", ".join(["(%s, %s, %s)"] * len(weighted_factors))
    params: list[Any] = []
    for factor_name, direction, raw_weight in weighted_factors:
        params.extend([factor_name, direction, raw_weight])
    params.extend([start_date, end_date, calc_version])
    sql = f"""
    WITH weight_input(factor_name, direction, raw_weight) AS (
        VALUES {values_sql}
    ),
    weights AS (
        SELECT
            factor_name,
            direction,
            raw_weight / NULLIF(SUM(ABS(raw_weight)) OVER (), 0) AS weight
        FROM weight_input
    ),
    factor_values AS (
        SELECT
            f.trade_date,
            f.asset_id,
            f.factor_name,
            f.factor_value::double precision AS factor_value,
            w.direction,
            w.weight
        FROM factor.factor_daily f
        JOIN weights w ON w.factor_name = f.factor_name
        WHERE f.trade_date BETWEEN %s AND %s
          AND f.calc_version = %s
          AND f.factor_value IS NOT NULL
    ),
    ranked AS (
        SELECT
            trade_date,
            asset_id,
            factor_name,
            weight,
            COUNT(*) OVER (PARTITION BY trade_date, factor_name) AS valid_count,
            COUNT(*) OVER (PARTITION BY trade_date, factor_name, factor_value) AS tie_count,
            CASE
                WHEN direction = 'higher'
                    THEN RANK() OVER (PARTITION BY trade_date, factor_name ORDER BY factor_value DESC)
                ELSE RANK() OVER (PARTITION BY trade_date, factor_name ORDER BY factor_value ASC)
            END AS base_rank
        FROM factor_values
    ),
    factor_scores AS (
        SELECT
            trade_date,
            asset_id,
            CASE
                WHEN valid_count = 1 THEN 100.0
                ELSE (
                    valid_count
                    - (base_rank + (tie_count - 1)::double precision / 2.0)
                ) / NULLIF(valid_count - 1, 0) * 100.0
            END * weight AS weighted_score
        FROM ranked
    ),
    composite AS (
        SELECT
            trade_date,
            asset_id,
            SUM(weighted_score) AS score_total
        FROM factor_scores
        GROUP BY trade_date, asset_id
    )
    SELECT
        trade_date,
        asset_id,
        RANK() OVER (PARTITION BY trade_date ORDER BY score_total DESC, asset_id ASC)::integer AS rank,
        score_total
    FROM composite
    ORDER BY trade_date, rank, asset_id
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def load_factor_rows(
    *,
    start_date: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    config = manual_v1_config()
    factor_names = list(config["factor_groups"].keys())
    sql = """
    SELECT trade_date, asset_id, factor_name, factor_value
    FROM factor.factor_daily
    WHERE trade_date BETWEEN %s AND %s
      AND factor_name = ANY(%s)
    ORDER BY trade_date, asset_id, factor_name
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [start_date, end_date, factor_names]))


def load_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, close, amount
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [adjust_type, start_date, end_date]))


def load_industry_memberships(
    *,
    start_date: str,
    end_date: str,
    industry_system: str = "csrc",
    industry_level: int = 1,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    daily_sql = """
    SELECT DISTINCT b.trade_date, b.asset_id, m.industry_name
    FROM market_daily_bar b
    JOIN core.industry_membership m
      ON m.asset_id = b.asset_id
     AND m.industry_system = %s
     AND m.level = %s
     AND m.start_date <= b.trade_date
     AND (m.end_date IS NULL OR m.end_date >= b.trade_date)
    WHERE b.adjust_type = 'hfq'
      AND b.trade_date BETWEEN %s AND %s
    ORDER BY b.trade_date, b.asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, daily_sql, [industry_system, industry_level, start_date, end_date])
    return pd.DataFrame(rows)


def write_industry_focus_outputs(
    *,
    output_dir: Path,
    start_date: str,
    end_date: str,
    industry_system: str,
    industry_scores: pd.DataFrame,
    focus_industries_daily: pd.DataFrame,
    top100_industry_daily: pd.DataFrame,
    summary: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    focus_coverage: pd.DataFrame,
    results: list[tuple[str, float, VectorizedTopNResult]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "industry_scores": str(output_dir / "industry_scores.csv"),
        "focus_industries_daily": str(output_dir / "focus_industries_daily.csv"),
        "top100_industry_daily": str(output_dir / "top100_industry_daily.csv"),
        "summary": str(output_dir / "summary.csv"),
        "monthly_returns": str(output_dir / "monthly_returns.csv"),
        "focus_coverage": str(output_dir / "focus_coverage.csv"),
        "markdown_report": str(output_dir / "industry_focus_score_report.md"),
    }
    industry_scores.to_csv(paths["industry_scores"], index=False)
    focus_industries_daily.to_csv(paths["focus_industries_daily"], index=False)
    top100_industry_daily.to_csv(paths["top100_industry_daily"], index=False)
    summary.to_csv(paths["summary"], index=False)
    monthly_returns.to_csv(paths["monthly_returns"], index=False)
    focus_coverage.to_csv(paths["focus_coverage"], index=False)

    for variant, cost, result in results:
        cost_label = _cost_label(cost)
        prefix = f"{variant}_cost{cost_label}"
        equity_path = output_dir / f"{prefix}_equity.csv"
        positions_path = output_dir / f"{prefix}_positions.csv"
        trades_path = output_dir / f"{prefix}_trades.csv"
        result.equity_curve.to_csv(equity_path, index=False)
        result.positions.to_csv(positions_path, index=False)
        result.trades.to_csv(trades_path, index=False)
        paths[f"{prefix}_equity"] = str(equity_path)
        paths[f"{prefix}_positions"] = str(positions_path)
        paths[f"{prefix}_trades"] = str(trades_path)

    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=start_date,
            end_date=end_date,
            industry_system=industry_system,
            summary=summary,
            focus_industries_daily=focus_industries_daily,
            focus_coverage=focus_coverage,
            monthly_returns=monthly_returns,
        ),
        encoding="utf-8",
    )
    return paths


def _merge_price_membership(prices: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    price_frame = _normalize_prices(prices)
    member_frame = _normalize_memberships(memberships)
    if price_frame.empty or member_frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name", "close", "amount"])
    return price_frame.merge(
        member_frame[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    ).dropna(subset=["close", "industry_name"])


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close", "amount"])
    frame = prices.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if "amount" not in frame.columns:
        frame["amount"] = 0.0
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    return frame.dropna(subset=["close"])


def _normalize_memberships(memberships: pd.DataFrame) -> pd.DataFrame:
    if memberships.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name"])
    frame = memberships.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["industry_name"] = frame["industry_name"].astype(str)
    return (
        frame.dropna(subset=["industry_name"])
        .sort_values(["trade_date", "asset_id", "industry_name"])
        .drop_duplicates(["trade_date", "asset_id"], keep="first")
        .reset_index(drop=True)
    )


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


def _add_stock_history_metrics(
    frame: pd.DataFrame,
    *,
    short_window: int,
    long_window: int,
) -> pd.DataFrame:
    data = frame.sort_values(["asset_id", "trade_date"]).copy()
    grouped = data.groupby("asset_id", group_keys=False)
    amount = data["amount"].fillna(0.0)
    data["amount"] = amount
    data["ret_5d"] = grouped["close"].pct_change(periods=min(5, short_window))
    data["ret_short"] = grouped["close"].pct_change(periods=short_window)
    data["ret_long"] = grouped["close"].pct_change(periods=long_window)
    data["one_day_return"] = grouped["close"].pct_change()
    data["ma_short"] = grouped["close"].transform(lambda s: s.rolling(short_window, min_periods=1).mean())
    data["ma_long"] = grouped["close"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    data["high_long"] = grouped["close"].transform(lambda s: s.rolling(long_window, min_periods=1).max())
    data["amount_ma5"] = grouped["amount"].transform(lambda s: s.rolling(min(5, short_window), min_periods=1).mean())
    data["amount_ma_short"] = grouped["amount"].transform(lambda s: s.rolling(short_window, min_periods=1).mean())
    data["amount_ma_long"] = grouped["amount"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    return data


def _aggregate_industry_daily(
    frame: pd.DataFrame,
    *,
    min_industry_stocks: int,
    short_window: int,
    long_window: int,
) -> pd.DataFrame:
    data = frame.copy()
    data["positive_short"] = data["ret_short"] > 0
    data["above_ma_short"] = data["close"] >= data["ma_short"]
    data["above_ma_long"] = data["close"] >= data["ma_long"]
    data["new_high_long"] = data["close"] >= data["high_long"]
    data["amount_ratio_5_short"] = data["amount_ma5"] / data["amount_ma_short"].replace(0, pd.NA)
    data["amount_ratio_short_long"] = data["amount_ma_short"] / data["amount_ma_long"].replace(0, pd.NA)
    data["amount_expanding"] = data["amount_ratio_5_short"] > 1.3
    data["near_high"] = data["close"] / data["high_long"].replace(0, pd.NA)
    grouped = data.groupby(["trade_date", "industry_name"], as_index=False)
    result = grouped.agg(
        stock_count=("asset_id", "nunique"),
        industry_ret_20d=("ret_short", "mean"),
        industry_ret_60d=("ret_long", "mean"),
        ret_5d=("ret_5d", "mean"),
        one_day_return_abs=("one_day_return", lambda s: s.abs().mean()),
        industry_amount_ratio_5_20=("amount_ratio_5_short", "mean"),
        industry_amount_ratio_20_60=("amount_ratio_short_long", "mean"),
        stock_amount_expansion_ratio=("amount_expanding", "mean"),
        up_ratio_20d=("positive_short", "mean"),
        above_ma20_ratio=("above_ma_short", "mean"),
        above_ma60_ratio=("above_ma_long", "mean"),
        new_high_60d_ratio=("new_high_long", "mean"),
        near_high_score=("near_high", "mean"),
        volatility_20d=("ret_short", "std"),
    )
    result = result[result["stock_count"] >= int(min_industry_stocks)].copy()
    if result.empty:
        return result

    market = data.groupby("trade_date", as_index=False).agg(
        market_ret_20d=("ret_short", "mean"),
        market_ret_60d=("ret_long", "mean"),
    )
    result = result.merge(market, on="trade_date", how="left")
    result["industry_excess_ret_20d"] = result["industry_ret_20d"] - result["market_ret_20d"]
    result["industry_excess_ret_60d"] = result["industry_ret_60d"] - result["market_ret_60d"]
    result["max_drawdown_20d"] = result["industry_ret_20d"].clip(upper=0.0)
    result["industry_trend_r2_20"] = (
        result.groupby("industry_name", group_keys=False)["industry_ret_20d"]
        .transform(lambda s: s.rolling(short_window, min_periods=1).corr(pd.Series(range(len(s)), index=s.index)))
        .abs()
    )
    return result.drop(columns=["market_ret_20d", "market_ret_60d"])


def _candidate_density_metrics(
    *,
    stock_scores: pd.DataFrame,
    memberships: pd.DataFrame,
    min_industry_stocks: int,
    top_candidate_count: int,
) -> pd.DataFrame:
    scores = _normalize_scores(stock_scores)
    members = _normalize_memberships(memberships)
    columns = [
        "trade_date",
        "industry_name",
        "top100_count",
        "top100_overweight_ratio",
        "top_decile_score_mean",
    ]
    if scores.empty or members.empty:
        return pd.DataFrame(columns=columns)
    joined = scores.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=columns)
    joined = joined.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True])
    joined["score_rank"] = joined.groupby("trade_date").cumcount() + 1
    joined["in_top_candidates"] = joined["score_rank"] <= int(top_candidate_count)
    industry_counts = joined.groupby(["trade_date", "industry_name"], as_index=False).agg(
        industry_score_count=("asset_id", "nunique"),
        top100_count=("in_top_candidates", "sum"),
        top_decile_score_mean=("score_total", lambda s: s.nlargest(max(1, int(len(s) * 0.1))).mean()),
    )
    totals = joined.groupby("trade_date", as_index=False).agg(total_score_count=("asset_id", "nunique"))
    industry_counts = industry_counts.merge(totals, on="trade_date", how="left")
    industry_counts["industry_share"] = industry_counts["industry_score_count"] / industry_counts["total_score_count"]
    industry_counts["top100_share"] = industry_counts["top100_count"] / float(top_candidate_count)
    industry_counts["top100_overweight_ratio"] = (
        industry_counts["top100_share"] / industry_counts["industry_share"].replace(0, pd.NA)
    )
    return industry_counts[industry_counts["industry_score_count"] >= int(min_industry_stocks)][columns]


def _build_composite_scores(frame: pd.DataFrame) -> pd.DataFrame:
    scored = frame.copy()
    fill_cols = [
        "industry_ret_20d",
        "industry_ret_60d",
        "industry_excess_ret_20d",
        "industry_excess_ret_60d",
        "industry_amount_ratio_5_20",
        "industry_amount_ratio_20_60",
        "stock_amount_expansion_ratio",
        "up_ratio_20d",
        "above_ma20_ratio",
        "above_ma60_ratio",
        "new_high_60d_ratio",
        "top100_count",
        "top100_overweight_ratio",
        "top_decile_score_mean",
        "industry_trend_r2_20",
        "near_high_score",
        "volatility_20d",
        "max_drawdown_20d",
        "ret_5d",
        "one_day_return_abs",
    ]
    for col in fill_cols:
        scored[col] = pd.to_numeric(scored[col], errors="coerce")
        scored[col] = scored.groupby("trade_date")[col].transform(lambda s: s.fillna(s.median()))
        scored[col] = scored[col].fillna(0.0)

    rank_specs = [
        ("industry_ret_20d", "industry_ret_20d_rank", True),
        ("industry_ret_60d", "industry_ret_60d_rank", True),
        ("industry_excess_ret_20d", "industry_excess_ret_20d_rank", True),
        ("industry_excess_ret_60d", "industry_excess_ret_60d_rank", True),
        ("up_ratio_20d", "up_ratio_20d_rank", True),
        ("above_ma20_ratio", "above_ma20_ratio_rank", True),
        ("above_ma60_ratio", "above_ma60_ratio_rank", True),
        ("new_high_60d_ratio", "new_high_60d_ratio_rank", True),
        ("industry_amount_ratio_5_20", "industry_amount_ratio_5_20_rank", True),
        ("industry_amount_ratio_20_60", "industry_amount_ratio_20_60_rank", True),
        ("stock_amount_expansion_ratio", "stock_amount_expansion_ratio_rank", True),
        ("top100_count", "top100_count_rank", True),
        ("top100_overweight_ratio", "top100_overweight_ratio_rank", True),
        ("top_decile_score_mean", "top_decile_score_mean_rank", True),
        ("industry_trend_r2_20", "industry_trend_r2_20_rank", True),
        ("near_high_score", "near_high_score_rank", True),
        ("max_drawdown_20d", "max_drawdown_20d_rank", True),
        ("volatility_20d", "volatility_20d_rank", False),
        ("ret_5d", "ret_5d_overheat_rank", True),
        ("one_day_return_abs", "one_day_return_abs_rank", True),
    ]
    for value_col, output_col, ascending in rank_specs:
        scored = rank_by_date(scored, value_col=value_col, output_col=output_col, ascending=ascending)

    scored["momentum_score"] = (
        0.35 * scored["industry_ret_20d_rank"]
        + 0.35 * scored["industry_ret_60d_rank"]
        + 0.15 * scored["industry_excess_ret_20d_rank"]
        + 0.15 * scored["industry_excess_ret_60d_rank"]
    )
    scored["breadth_score"] = (
        0.30 * scored["up_ratio_20d_rank"]
        + 0.30 * scored["above_ma20_ratio_rank"]
        + 0.20 * scored["above_ma60_ratio_rank"]
        + 0.20 * scored["new_high_60d_ratio_rank"]
    )
    scored["volume_score"] = (
        0.40 * scored["industry_amount_ratio_5_20_rank"]
        + 0.35 * scored["industry_amount_ratio_20_60_rank"]
        + 0.25 * scored["stock_amount_expansion_ratio_rank"]
    )
    scored["candidate_density_score"] = (
        0.45 * scored["top100_count_rank"]
        + 0.35 * scored["top100_overweight_ratio_rank"]
        + 0.20 * scored["top_decile_score_mean_rank"]
    )
    scored["quality_score"] = (
        0.35 * scored["industry_trend_r2_20_rank"]
        + 0.25 * scored["near_high_score_rank"]
        + 0.20 * scored["max_drawdown_20d_rank"]
        + 0.20 * scored["volatility_20d_rank"]
    )
    scored["overheat_penalty"] = (
        0.35 * scored["ret_5d_overheat_rank"]
        + 0.30 * scored["industry_amount_ratio_5_20_rank"]
        + 0.20 * (1.0 - scored["volatility_20d_rank"])
        + 0.15 * scored["one_day_return_abs_rank"]
    )
    scored["industry_focus_score"] = (
        0.30 * scored["momentum_score"]
        + 0.20 * scored["breadth_score"]
        + 0.20 * scored["volume_score"]
        + 0.20 * scored["candidate_density_score"]
        + 0.10 * scored["quality_score"]
        - 0.10 * scored["overheat_penalty"]
    )
    return scored


def _normalize_industry_scores(industry_scores: pd.DataFrame) -> pd.DataFrame:
    if industry_scores.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "industry_focus_score"])
    scores = industry_scores.copy()
    scores["trade_date"] = scores["trade_date"].map(_iso_date)
    scores["industry_name"] = scores["industry_name"].astype(str)
    scores["industry_focus_score"] = pd.to_numeric(scores["industry_focus_score"], errors="coerce")
    return scores.dropna(subset=["industry_focus_score"])


def _add_rank_number(scores: pd.DataFrame) -> pd.DataFrame:
    ranked = scores.sort_values(
        ["trade_date", "industry_focus_score", "industry_name"],
        ascending=[True, False, True],
    ).copy()
    ranked["focus_rank"] = ranked.groupby("trade_date").cumcount() + 1
    ranked["score_percentile"] = ranked.groupby("trade_date")["industry_focus_score"].rank(
        method="average",
        pct=True,
        ascending=True,
    )
    return ranked


def _empty_focus_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=FOCUS_COLUMNS)


def _top100_industry_daily(stock_scores: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    scores = _normalize_scores(stock_scores)
    members = _normalize_memberships(memberships)
    columns = ["trade_date", "industry_name", "top100_count", "top100_avg_score"]
    if scores.empty or members.empty:
        return pd.DataFrame(columns=columns)
    joined = scores.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    joined = joined.sort_values(["trade_date", "score_total"], ascending=[True, False])
    joined["rank"] = joined.groupby("trade_date").cumcount() + 1
    top = joined[joined["rank"] <= 100]
    if top.empty:
        return pd.DataFrame(columns=columns)
    return top.groupby(["trade_date", "industry_name"], as_index=False).agg(
        top100_count=("asset_id", "nunique"),
        top100_avg_score=("score_total", "mean"),
    )


def _focus_coverage_by_variant(
    stock_scores: pd.DataFrame,
    memberships: pd.DataFrame,
    focus_frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    top20 = _normalize_scores(stock_scores)
    top20 = top20[top20["rank"] <= 20].copy()
    members = _normalize_memberships(memberships)
    if top20.empty or members.empty:
        return pd.DataFrame(columns=["variant", "trade_date", "focus_count", "focus_ratio"])
    top20 = top20.merge(
        members[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="left",
    )
    rows: list[dict[str, Any]] = []
    for variant, focus in focus_frames.items():
        allowed = focus[["trade_date", "industry_name"]].drop_duplicates()
        tagged = top20.merge(
            allowed.assign(in_focus=True),
            on=["trade_date", "industry_name"],
            how="left",
        )
        tagged["in_focus"] = tagged["in_focus"].fillna(False)
        daily = tagged.groupby("trade_date", as_index=False).agg(
            focus_count=("in_focus", "sum"),
            total_count=("asset_id", "nunique"),
        )
        daily["variant"] = variant
        daily["focus_ratio"] = daily["focus_count"] / daily["total_count"].replace(0, pd.NA)
        rows.extend(daily[["variant", "trade_date", "focus_count", "focus_ratio"]].to_dict("records"))
    return pd.DataFrame(rows)


def _monthly_returns(results: list[tuple[str, float, VectorizedTopNResult]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, cost, result in results:
        equity = result.equity_curve.copy()
        if equity.empty:
            continue
        equity["month"] = pd.to_datetime(equity["date"]).dt.to_period("M").astype(str)
        for month, group in equity.groupby("month"):
            month_return = (1.0 + group["net_return"]).prod() - 1.0
            rows.append(
                {
                    "variant": variant,
                    "transaction_cost_bps": cost,
                    "month": month,
                    "monthly_return": month_return,
                }
            )
    return pd.DataFrame(rows)


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    industry_system: str,
    summary: pd.DataFrame,
    focus_industries_daily: pd.DataFrame,
    focus_coverage: pd.DataFrame,
    monthly_returns: pd.DataFrame,
) -> str:
    focus_counts = (
        focus_industries_daily.groupby("selection_mode")
        .agg(rows=("industry_name", "size"), avg_industries_per_day=("industry_name", lambda s: len(s) / max(1, s.index.nunique())))
        .reset_index()
        if not focus_industries_daily.empty
        else pd.DataFrame()
    )
    coverage_summary = (
        focus_coverage.groupby("variant", as_index=False).agg(
            avg_focus_count=("focus_count", "mean"),
            avg_focus_ratio=("focus_ratio", "mean"),
        )
        if not focus_coverage.empty
        else pd.DataFrame()
    )
    return "\n".join(
        [
            "# Industry Focus Score V1",
            "",
            f"Period: {start_date} to {end_date}",
            f"Industry system: {industry_system}",
            "",
            "Point-in-time rule: industry scores use only data with trade_date on or before each score date.",
            "",
            "## Score Formula",
            "",
            "`industry_focus_score = 0.30 momentum + 0.20 breadth + 0.20 volume + 0.20 candidate_density + 0.10 quality - 0.10 overheat_penalty`",
            "",
            "## Summary",
            "",
            summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
            "",
            "## Monthly Returns",
            "",
            monthly_returns.to_markdown(index=False) if not monthly_returns.empty else "No monthly returns.",
            "",
            "## Focus Selection Rows",
            "",
            focus_counts.to_markdown(index=False) if not focus_counts.empty else "No focus industries selected.",
            "",
            "## Original Top20 Focus Coverage",
            "",
            coverage_summary.to_markdown(index=False) if not coverage_summary.empty else "No coverage rows.",
            "",
            "## Data Notes",
            "",
            "- Fixed focus industries are labeled `fixed_ex_post` and are diagnostic only.",
            "- Dynamic modes are the valid point-in-time candidates for historical evaluation.",
            "- Fundamental data is not used in this V1 score.",
            "- This phase does not replace production Top20 reports.",
        ]
    )


def _cost_label(cost: float) -> str:
    return str(int(cost)) if float(cost).is_integer() else str(cost).replace(".", "p")


def _month_chunks(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    chunks: list[tuple[str, str]] = []
    current = pd.Timestamp(start).replace(day=1)
    while current.date() <= end:
        month_start = max(current.date(), start)
        month_end = min((current + pd.offsets.MonthEnd(0)).date(), end)
        chunks.append((month_start.isoformat(), month_end.isoformat()))
        current = current + pd.offsets.MonthBegin(1)
    return chunks


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
