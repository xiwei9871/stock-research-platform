from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.intraday_risk_filter_backtest import (
    _concat_frames,
    _format_number,
    _format_pct,
    _result_metrics,
    _tag_frame,
    classify_variant_recommendation,
)
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)


V2_FEATURES = [
    "amount_front_1h_ratio",
    "intraday_volatility_5min",
    "morning_return",
    "afternoon_return",
    "last_30m_return",
    "close_to_vwap",
]

V2_SUMMARY_COLUMNS = [
    "top_n",
    "variant_name",
    "final_equity",
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "average_turnover",
    "total_transaction_cost",
    "average_holdings_count",
    "minimum_holdings_count",
    "midtrend_risk_candidate_count",
    "midtrend_high_candidate_count",
    "penalized_candidate_count",
    "total_return_delta_vs_baseline",
    "max_drawdown_delta_vs_baseline",
    "recommendation",
]


def build_intraday_risk_signals_v2(
    features: pd.DataFrame,
    *,
    lookback: int = 20,
    zscore_threshold: float = 1.5,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "front_loaded_failure",
        "morning_to_afternoon_reversal",
        "tail_confirmation_failure",
        "high_volatility_no_follow_through",
        "structural_risk_count",
        "lhb_risk_level",
    ]
    if features.empty:
        return pd.DataFrame(columns=columns)

    wide = _pivot_features(features)
    if wide.empty:
        return pd.DataFrame(columns=columns)

    for feature_name in [
        "amount_front_1h_ratio",
        "intraday_volatility_5min",
        "morning_return",
        "afternoon_return",
        "last_30m_return",
        "close_to_vwap",
    ]:
        if feature_name in wide.columns:
            wide[f"{feature_name}_zscore"] = _prior_rolling_zscore(
                wide,
                feature_name,
                lookback=lookback,
            )

    front_z = wide.get("amount_front_1h_ratio_zscore", pd.Series(0.0, index=wide.index))
    vol_z = wide.get("intraday_volatility_5min_zscore", pd.Series(0.0, index=wide.index))
    tail_z = wide.get("last_30m_return_zscore", pd.Series(0.0, index=wide.index))
    vwap_z = wide.get("close_to_vwap_zscore", pd.Series(0.0, index=wide.index))
    morning_z = wide.get("morning_return_zscore", pd.Series(0.0, index=wide.index))
    afternoon_z = wide.get("afternoon_return_zscore", pd.Series(0.0, index=wide.index))
    afternoon = wide.get("afternoon_return", pd.Series(0.0, index=wide.index))
    morning = wide.get("morning_return", pd.Series(0.0, index=wide.index))
    last_30m = wide.get("last_30m_return", pd.Series(0.0, index=wide.index))
    close_to_vwap = wide.get("close_to_vwap", pd.Series(0.0, index=wide.index))

    wide["front_loaded_failure"] = (
        front_z.ge(zscore_threshold)
        & (afternoon.lt(0.0) | afternoon_z.le(-zscore_threshold))
    )
    wide["morning_to_afternoon_reversal"] = (
        morning.gt(0.0)
        & afternoon.lt(0.0)
        & morning_z.ge(zscore_threshold)
        & afternoon_z.le(-zscore_threshold)
    )
    wide["tail_confirmation_failure"] = (
        last_30m.lt(0.0)
        & close_to_vwap.lt(0.0)
        & tail_z.le(-zscore_threshold)
        & vwap_z.le(-zscore_threshold)
    )
    wide["high_volatility_no_follow_through"] = (
        vol_z.ge(zscore_threshold) & (close_to_vwap.lt(0.0) | afternoon.lt(0.0))
    )
    flag_cols = [
        "front_loaded_failure",
        "morning_to_afternoon_reversal",
        "tail_confirmation_failure",
        "high_volatility_no_follow_through",
    ]
    wide["structural_risk_count"] = wide[flag_cols].sum(axis=1).astype(int)
    wide["lhb_risk_level"] = "none"
    wide.loc[wide["structural_risk_count"].eq(1), "lhb_risk_level"] = "watch"
    wide.loc[wide["structural_risk_count"].ge(2), "lhb_risk_level"] = "high"
    return wide[columns].sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def build_midtrend_risk_states(
    signals: pd.DataFrame,
    *,
    watch_5d_count: int = 2,
    high_5d_count: int = 3,
    watch_10d_count: int = 3,
    high_10d_count: int = 5,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "midtrend_risk_trigger",
        "midtrend_risk_trigger_count_5d",
        "midtrend_risk_trigger_count_10d",
        "midtrend_risk_level",
    ]
    if signals.empty:
        return pd.DataFrame(columns=columns)

    frame = signals.dropna(subset=["trade_date", "asset_id"]).copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["structural_risk_count"] = pd.to_numeric(
        frame.get("structural_risk_count", 0),
        errors="coerce",
    ).fillna(0)
    frame = frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    frame["midtrend_risk_trigger"] = frame["structural_risk_count"].gt(0)
    frame["midtrend_high_risk_trigger"] = frame["structural_risk_count"].ge(2)
    trigger = frame["midtrend_risk_trigger"].astype(int)
    high_trigger = frame["midtrend_high_risk_trigger"].astype(int)
    frame["midtrend_risk_trigger_count_5d"] = (
        trigger.groupby(frame["asset_id"]).transform(lambda s: s.rolling(5, min_periods=1).sum())
    )
    frame["midtrend_risk_trigger_count_10d"] = (
        trigger.groupby(frame["asset_id"]).transform(lambda s: s.rolling(10, min_periods=1).sum())
    )
    frame["midtrend_high_risk_trigger_count_5d"] = (
        high_trigger.groupby(frame["asset_id"]).transform(lambda s: s.rolling(5, min_periods=1).sum())
    )
    frame["midtrend_high_risk_trigger_count_10d"] = (
        high_trigger.groupby(frame["asset_id"]).transform(lambda s: s.rolling(10, min_periods=1).sum())
    )
    frame["midtrend_risk_level"] = "none"
    watch_mask = (
        frame["midtrend_risk_trigger_count_5d"].ge(watch_5d_count)
        | frame["midtrend_risk_trigger_count_10d"].ge(watch_10d_count)
    )
    high_mask = (
        frame["midtrend_high_risk_trigger_count_5d"].ge(high_5d_count)
        | frame["midtrend_high_risk_trigger_count_10d"].ge(high_10d_count)
    )
    frame.loc[watch_mask, "midtrend_risk_level"] = "watch"
    frame.loc[high_mask, "midtrend_risk_level"] = "high"
    return frame[columns].sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def build_midtrend_score_variants_v2(
    scores: pd.DataFrame,
    states: pd.DataFrame,
    *,
    watch_penalty: float = 3.0,
    high_penalty: float = 8.0,
) -> dict[str, pd.DataFrame]:
    baseline = _normalize_scores(scores)
    flagged = _attach_midtrend_states(baseline, states)

    penalty = flagged.copy()
    penalty["score_total"] = penalty["score_total"] - penalty[
        "midtrend_risk_level"
    ].map({"none": 0.0, "watch": watch_penalty, "high": high_penalty}).fillna(0.0)
    penalty = _rerank_scores(penalty)

    confirmed = flagged.copy()
    confirmed["score_total"] = confirmed["score_total"] - confirmed[
        "midtrend_risk_level"
    ].map({"none": 0.0, "watch": watch_penalty, "high": high_penalty * 2.0}).fillna(0.0)
    confirmed = _rerank_scores(confirmed)

    output_columns = ["trade_date", "asset_id", "rank", "score_total"]
    return {
        "baseline_topn": baseline,
        "trend_new_entry_penalty": penalty[output_columns],
        "trend_confirmed_reduce": confirmed[output_columns],
    }


def run_intraday_risk_control_v2_from_frames(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    features: pd.DataFrame,
    start_date: object,
    end_date: object,
    top_n_values: list[int],
    *,
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    lookback: int = 20,
    zscore_threshold: float = 1.5,
    watch_penalty: float = 3.0,
    high_penalty: float = 8.0,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    signals = build_intraday_risk_signals_v2(
        features,
        lookback=lookback,
        zscore_threshold=zscore_threshold,
    )
    states = build_midtrend_risk_states(signals)
    variants = build_midtrend_score_variants_v2(
        scores,
        states,
        watch_penalty=watch_penalty,
        high_penalty=high_penalty,
    )
    backtests: dict[tuple[int, str], dict[str, Any]] = {}
    equity_frames = []
    position_frames = []
    trade_frames = []

    for top_n in top_n_values:
        for variant_name, variant_scores in variants.items():
            config = VectorizedTopNConfig(
                start_date=start_date,
                end_date=end_date,
                top_n=int(top_n),
                rebalance_frequency=rebalance_frequency,
                transaction_cost_bps=transaction_cost_bps,
            )
            result = run_vectorized_topn_backtest(variant_scores, prices, config)
            backtests[(int(top_n), variant_name)] = {
                "result": result,
                "scores": variant_scores,
            }
            equity_frames.append(_tag_frame(result.equity_curve, int(top_n), variant_name))
            position_frames.append(_tag_frame(result.positions, int(top_n), variant_name))
            trade_frames.append(_tag_frame(result.trades, int(top_n), variant_name))

    result_dict = {
        "summary": summarize_intraday_risk_control_v2(backtests, states, top_n_values),
        "signals": signals,
        "states": states,
        "equity": _concat_frames(equity_frames),
        "positions": _concat_frames(position_frames),
        "trades": _concat_frames(trade_frames),
        "backtests": backtests,
    }
    if output_dir is not None:
        result_dict["paths"] = write_intraday_risk_control_v2_report(result_dict, output_dir)
    return result_dict


def load_intraday_risk_control_v2_inputs(
    start_date: object,
    end_date: object,
    *,
    score_version: str = "manual_v1",
    score_adjust_type: str = "hfq",
    intraday_freq: str = "5min",
    intraday_adjust_type: str = "raw",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    score_sql = """
    SELECT trade_date, asset_id, rank, score_total
    FROM factor.stock_score_daily
    WHERE score_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, rank, asset_id
    """
    price_sql = """
    SELECT trade_date, asset_id, open, close, amount, trade_status,
           false AS is_limit_up, false AS is_limit_down, false AS is_suspended
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    feature_sql = """
    SELECT trade_date, asset_id, feature_name, feature_value
    FROM factor.stock_intraday_features_daily
    WHERE feature_name = ANY(%s)
      AND freq = %s
      AND adjust_type = %s
      AND trade_date BETWEEN %s AND %s
      AND calc_version = 'intraday_v1'
    ORDER BY trade_date, asset_id, feature_name
    """
    with connect(service) as conn:
        score_rows = fetch_all(conn, score_sql, [score_version, start_date, end_date])
        price_rows = fetch_all(conn, price_sql, [score_adjust_type, start_date, end_date])
        feature_rows = fetch_all(
            conn,
            feature_sql,
            [V2_FEATURES, intraday_freq, intraday_adjust_type, start_date, end_date],
        )
    return pd.DataFrame(score_rows), pd.DataFrame(price_rows), pd.DataFrame(feature_rows)


def run_intraday_risk_control_v2_backtest(
    start_date: object,
    end_date: object,
    output_dir: str | Path,
    *,
    score_version: str = "manual_v1",
    top_n_values: list[int] | None = None,
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    score_adjust_type: str = "hfq",
    intraday_freq: str = "5min",
    intraday_adjust_type: str = "raw",
    lookback: int = 20,
    zscore_threshold: float = 1.5,
    watch_penalty: float = 3.0,
    high_penalty: float = 8.0,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    scores, prices, features = load_intraday_risk_control_v2_inputs(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        score_adjust_type=score_adjust_type,
        intraday_freq=intraday_freq,
        intraday_adjust_type=intraday_adjust_type,
        service=service,
    )
    return run_intraday_risk_control_v2_from_frames(
        scores=scores,
        prices=prices,
        features=features,
        start_date=start_date,
        end_date=end_date,
        top_n_values=[10, 20] if top_n_values is None else list(top_n_values),
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        lookback=lookback,
        zscore_threshold=zscore_threshold,
        watch_penalty=watch_penalty,
        high_penalty=high_penalty,
        output_dir=output_dir,
    )


def summarize_intraday_risk_control_v2(
    backtests: dict[tuple[int, str], dict[str, Any]],
    states: pd.DataFrame,
    top_n_values: list[int],
) -> pd.DataFrame:
    rows = []
    variant_order = ["baseline_topn", "trend_new_entry_penalty", "trend_confirmed_reduce"]
    for top_n in top_n_values:
        baseline_entry = backtests.get((int(top_n), "baseline_topn"))
        baseline_result = baseline_entry["result"] if baseline_entry else None
        baseline_metrics = _result_metrics(baseline_result) if baseline_result is not None else {}
        baseline_scores = baseline_entry.get("scores", pd.DataFrame()) if baseline_entry else pd.DataFrame()
        baseline_risk_count = _candidate_count_for_levels(
            baseline_scores,
            states,
            {"watch", "high"},
        )
        baseline_high_count = _candidate_count_for_levels(baseline_scores, states, {"high"})

        for variant_name in variant_order:
            entry = backtests.get((int(top_n), variant_name))
            if entry is None:
                continue
            metrics = _result_metrics(entry["result"])
            return_delta = float(metrics["total_return"]) - float(
                baseline_metrics.get("total_return", metrics["total_return"])
            )
            drawdown_delta = float(metrics["max_drawdown"]) - float(
                baseline_metrics.get("max_drawdown", metrics["max_drawdown"])
            )
            recommendation = (
                "baseline"
                if variant_name == "baseline_topn"
                else classify_variant_recommendation(
                    baseline_total_return=float(baseline_metrics.get("total_return", 0.0)),
                    variant_total_return=float(metrics["total_return"]),
                    baseline_max_drawdown=float(baseline_metrics.get("max_drawdown", 0.0)),
                    variant_max_drawdown=float(metrics["max_drawdown"]),
                )
            )
            rows.append(
                {
                    "top_n": int(top_n),
                    "variant_name": variant_name,
                    **metrics,
                    "midtrend_risk_candidate_count": baseline_risk_count,
                    "midtrend_high_candidate_count": baseline_high_count,
                    "penalized_candidate_count": (
                        baseline_risk_count if variant_name != "baseline_topn" else 0
                    ),
                    "total_return_delta_vs_baseline": return_delta,
                    "max_drawdown_delta_vs_baseline": drawdown_delta,
                    "recommendation": recommendation,
                }
            )
    return pd.DataFrame(rows).reindex(columns=V2_SUMMARY_COLUMNS)


def write_intraday_risk_control_v2_report(
    result: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_path / "intraday_risk_control_v2_summary.csv",
        "signals": output_path / "intraday_risk_control_v2_signals.csv",
        "states": output_path / "intraday_risk_control_v2_states.csv",
        "positions": output_path / "intraday_risk_control_v2_positions.csv",
        "trades": output_path / "intraday_risk_control_v2_trades.csv",
        "report": output_path / "intraday_risk_control_v2_report.md",
    }
    result.get("summary", pd.DataFrame()).to_csv(paths["summary"], index=False)
    result.get("signals", pd.DataFrame()).to_csv(paths["signals"], index=False)
    result.get("states", pd.DataFrame()).to_csv(paths["states"], index=False)
    result.get("positions", pd.DataFrame()).to_csv(paths["positions"], index=False)
    result.get("trades", pd.DataFrame()).to_csv(paths["trades"], index=False)
    paths["report"].write_text(
        format_intraday_risk_control_v2_report(result.get("summary", pd.DataFrame())),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in paths.items()}


def format_intraday_risk_control_v2_report(summary: pd.DataFrame) -> str:
    lines = ["# Intraday Risk Control V2 Backtest", "", "## Baseline Comparison"]
    if summary.empty:
        lines.extend(["No variant summary rows were produced.", ""])
        return "\n".join(lines).rstrip() + "\n"

    for top_n, group in summary.groupby("top_n", sort=True):
        baseline = group[group["variant_name"].eq("baseline_topn")]
        if baseline.empty:
            continue
        base = baseline.iloc[0]
        lines.append(f"### TopN {int(top_n)}")
        lines.append(
            "- baseline_topn: "
            f"total_return={_format_pct(base.get('total_return'))}, "
            f"max_drawdown={_format_pct(base.get('max_drawdown'))}, "
            f"sharpe={_format_number(base.get('sharpe_ratio'))}"
        )
        for _, row in group[~group["variant_name"].eq("baseline_topn")].iterrows():
            lines.append(
                f"- {row['variant_name']}: "
                f"total_return_delta={_format_pct(row.get('total_return_delta_vs_baseline'))}, "
                f"max_drawdown_delta={_format_pct(row.get('max_drawdown_delta_vs_baseline'))}, "
                f"sharpe={_format_number(row.get('sharpe_ratio'))}, "
                f"recommendation={row.get('recommendation')}"
            )
        lines.append("")
    lines.extend(["## Variant Summary", summary.to_markdown(index=False)])
    return "\n".join(lines).rstrip() + "\n"


def _pivot_features(features: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "asset_id", "feature_name", "feature_value"}
    if not required.issubset(features.columns):
        return pd.DataFrame()
    frame = features.dropna(subset=["trade_date", "asset_id", "feature_name"]).copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["feature_value"] = pd.to_numeric(frame["feature_value"], errors="coerce")
    return (
        frame.pivot_table(
            index=["trade_date", "asset_id"],
            columns="feature_name",
            values="feature_value",
            aggfunc="last",
        )
        .reset_index()
        .rename_axis(None, axis=1)
        .sort_values(["asset_id", "trade_date"])
        .reset_index(drop=True)
    )


def _prior_rolling_zscore(
    frame: pd.DataFrame,
    feature_name: str,
    *,
    lookback: int,
) -> pd.Series:
    values = pd.to_numeric(frame[feature_name], errors="coerce")
    grouped = values.groupby(frame["asset_id"])
    prior_mean = grouped.transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=2).mean()
    )
    prior_std = grouped.transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=2).std(ddof=1)
    )
    zscore = (values - prior_mean) / prior_std.replace(0.0, pd.NA)
    return pd.to_numeric(zscore, errors="coerce").fillna(0.0)


def _safe_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=frame.index)


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    output_columns = ["trade_date", "asset_id", "rank", "score_total"]
    if scores.empty or any(column not in scores.columns for column in output_columns):
        return pd.DataFrame(columns=output_columns)
    frame = scores.dropna(subset=["trade_date", "asset_id"]).copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    return frame[output_columns].dropna(subset=["trade_date", "asset_id", "score_total"])


def _attach_midtrend_states(scores: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    result = scores.copy()
    if states.empty:
        result["midtrend_risk_level"] = "none"
        result["midtrend_risk_trigger_count_5d"] = 0
        result["midtrend_risk_trigger_count_10d"] = 0
        return result

    state_cols = [
        "trade_date",
        "asset_id",
        "midtrend_risk_level",
        "midtrend_risk_trigger_count_5d",
        "midtrend_risk_trigger_count_10d",
    ]
    normalized_states = states[state_cols].dropna(subset=["trade_date", "asset_id"]).copy()
    normalized_states["trade_date"] = normalized_states["trade_date"].astype(str).str[:10]
    normalized_states["asset_id"] = normalized_states["asset_id"].astype(str)
    result = result.merge(normalized_states, on=["trade_date", "asset_id"], how="left")
    result["midtrend_risk_level"] = result["midtrend_risk_level"].fillna("none")
    for column in ["midtrend_risk_trigger_count_5d", "midtrend_risk_trigger_count_10d"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    return result


def _rerank_scores(scores: pd.DataFrame) -> pd.DataFrame:
    ranked = scores.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).copy()
    ranked["rank"] = ranked.groupby("trade_date").cumcount() + 1
    return ranked.reset_index(drop=True)


def _candidate_count_for_levels(
    scores: pd.DataFrame,
    states: pd.DataFrame,
    levels: set[str],
) -> int:
    if scores.empty:
        return 0
    flagged = _attach_midtrend_states(_normalize_scores(scores), states)
    return int(flagged["midtrend_risk_level"].isin(levels).sum())
