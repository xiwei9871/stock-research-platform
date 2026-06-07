from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)

RISK_FEATURES = [
    "intraday_volatility_5min",
    "amount_front_1h_ratio",
    "last_30m_return",
    "afternoon_return",
    "close_to_vwap",
]

RISK_FLAG_MAP = {
    "intraday_volatility_5min": ("high_intraday_volatility", "high"),
    "amount_front_1h_ratio": ("high_front_loaded_amount", "high"),
    "last_30m_return": ("weak_last_30m", "low"),
    "afternoon_return": ("weak_afternoon", "low"),
    "close_to_vwap": ("weak_close_to_vwap", "low"),
}

SUMMARY_COLUMNS = [
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
    "risk_flagged_candidate_count",
    "excluded_high_risk_count",
    "penalized_candidate_count",
    "total_return_delta_vs_baseline",
    "max_drawdown_delta_vs_baseline",
    "recommendation",
]


def _empty_risk_flags_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.Series(dtype=object),
            "asset_id": pd.Series(dtype=object),
            "high_intraday_volatility": pd.Series(dtype=bool),
            "high_front_loaded_amount": pd.Series(dtype=bool),
            "weak_last_30m": pd.Series(dtype=bool),
            "weak_afternoon": pd.Series(dtype=bool),
            "weak_close_to_vwap": pd.Series(dtype=bool),
            "intraday_risk_flag_count": pd.Series(dtype=int),
            "intraday_risk_level": pd.Series(dtype=object),
        }
    )


def build_intraday_risk_flags(features: pd.DataFrame, quantile: float = 0.2) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "high_intraday_volatility",
        "high_front_loaded_amount",
        "weak_last_30m",
        "weak_afternoon",
        "weak_close_to_vwap",
        "intraday_risk_flag_count",
        "intraday_risk_level",
    ]
    if features.empty:
        return _empty_risk_flags_frame()

    frame = features.dropna(subset=["trade_date", "asset_id"]).copy()
    if frame.empty:
        return _empty_risk_flags_frame()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["feature_value"] = pd.to_numeric(frame["feature_value"], errors="coerce")
    wide = (
        frame.pivot_table(
            index=["trade_date", "asset_id"],
            columns="feature_name",
            values="feature_value",
            aggfunc="last",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for flag_name, _direction in RISK_FLAG_MAP.values():
        wide[flag_name] = False
    for feature_name, (flag_name, direction) in RISK_FLAG_MAP.items():
        if feature_name not in wide.columns:
            continue
        if direction == "high":
            thresholds = wide.groupby("trade_date")[feature_name].transform(
                lambda s: s.quantile(1.0 - quantile)
            )
            wide[flag_name] = wide[feature_name] >= thresholds
        else:
            thresholds = wide.groupby("trade_date")[feature_name].transform(
                lambda s: s.quantile(quantile)
            )
            wide[flag_name] = wide[feature_name] <= thresholds
        wide[flag_name] = wide[flag_name].fillna(False)
    flag_cols = [item[0] for item in RISK_FLAG_MAP.values()]
    wide["intraday_risk_flag_count"] = wide[flag_cols].sum(axis=1).astype(int)
    wide["intraday_risk_level"] = "none"
    wide.loc[wide["intraday_risk_flag_count"].eq(1), "intraday_risk_level"] = "watch"
    wide.loc[wide["intraday_risk_flag_count"].ge(2), "intraday_risk_level"] = "high"
    return wide[columns].sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def build_score_variants(
    scores: pd.DataFrame,
    flags: pd.DataFrame,
    *,
    watch_penalty: float = 5.0,
    high_penalty: float = 15.0,
) -> dict[str, pd.DataFrame]:
    baseline = _normalize_scores(scores)
    flagged = _attach_flags(baseline, flags)

    exclude = flagged[~flagged["intraday_risk_level"].eq("high")].copy()
    exclude = _rerank_scores(exclude)

    penalty = flagged.copy()
    penalty["score_total"] = penalty["score_total"] - penalty["intraday_risk_level"].map(
        {"none": 0.0, "watch": watch_penalty, "high": high_penalty}
    ).fillna(0.0)
    penalty = _rerank_scores(penalty)

    output_columns = ["trade_date", "asset_id", "rank", "score_total"]
    return {
        "baseline_topn": baseline,
        "exclude_high_risk": exclude[output_columns],
        "penalty_high_risk": penalty[output_columns],
    }


def classify_variant_recommendation(
    baseline_total_return: float,
    variant_total_return: float,
    baseline_max_drawdown: float,
    variant_max_drawdown: float,
) -> str:
    drawdown_improvement = float(variant_max_drawdown) - float(baseline_max_drawdown)
    return_delta = float(variant_total_return) - float(baseline_total_return)
    epsilon = 1e-12
    if drawdown_improvement + epsilon < 0.01:
        return "reject"
    if return_delta + epsilon >= -0.02:
        return "promote_for_shadow_review"
    return "watch_only"


def run_intraday_risk_filter_backtest_from_frames(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    features: pd.DataFrame,
    start_date: object,
    end_date: object,
    top_n_values: list[int],
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    flags = build_intraday_risk_flags(features)
    variants = build_score_variants(scores, flags)
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

    summary = summarize_variant_backtests(backtests, flags, top_n_values)
    result_dict = {
        "summary": summary,
        "flags": flags,
        "equity": _concat_frames(equity_frames),
        "positions": _concat_frames(position_frames),
        "trades": _concat_frames(trade_frames),
        "backtests": backtests,
    }
    if output_dir is not None:
        result_dict["paths"] = write_intraday_risk_filter_report(result_dict, output_dir)
    return result_dict


def load_intraday_risk_filter_inputs(
    start_date: object,
    end_date: object,
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
            [RISK_FEATURES, intraday_freq, intraday_adjust_type, start_date, end_date],
        )
    return pd.DataFrame(score_rows), pd.DataFrame(price_rows), pd.DataFrame(feature_rows)


def run_intraday_risk_filter_backtest(
    start_date: object,
    end_date: object,
    output_dir: str | Path,
    score_version: str = "manual_v1",
    top_n_values: list[int] | None = None,
    rebalance_frequency: str = "daily",
    transaction_cost_bps: float = 20.0,
    score_adjust_type: str = "hfq",
    intraday_freq: str = "5min",
    intraday_adjust_type: str = "raw",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    resolved_top_n_values = [10, 20] if top_n_values is None else list(top_n_values)
    scores, prices, features = load_intraday_risk_filter_inputs(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        score_adjust_type=score_adjust_type,
        intraday_freq=intraday_freq,
        intraday_adjust_type=intraday_adjust_type,
        service=service,
    )
    return run_intraday_risk_filter_backtest_from_frames(
        scores=scores,
        prices=prices,
        features=features,
        start_date=start_date,
        end_date=end_date,
        top_n_values=resolved_top_n_values,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        output_dir=output_dir,
    )


def summarize_variant_backtests(
    backtests: dict[tuple[int, str], dict[str, Any]],
    flags: pd.DataFrame,
    top_n_values: list[int],
) -> pd.DataFrame:
    rows = []
    for top_n in top_n_values:
        baseline_entry = backtests.get((int(top_n), "baseline_topn"))
        baseline_result = baseline_entry["result"] if baseline_entry else None
        baseline_metrics = _result_metrics(baseline_result) if baseline_result is not None else {}
        baseline_scores = baseline_entry.get("scores", pd.DataFrame()) if baseline_entry else pd.DataFrame()
        baseline_risk_flagged_count = _risk_flagged_candidate_count(baseline_scores, flags)
        baseline_high_count = _candidate_count_for_level(baseline_scores, flags, "high")

        for variant_name in ["baseline_topn", "exclude_high_risk", "penalty_high_risk"]:
            entry = backtests.get((int(top_n), variant_name))
            if entry is None:
                continue
            result = entry["result"]
            variant_scores = entry.get("scores", pd.DataFrame())
            metrics = _result_metrics(result)
            return_delta = float(metrics["total_return"]) - float(
                baseline_metrics.get("total_return", metrics["total_return"])
            )
            drawdown_delta = float(metrics["max_drawdown"]) - float(
                baseline_metrics.get("max_drawdown", metrics["max_drawdown"])
            )
            if variant_name == "baseline_topn":
                recommendation = "baseline"
            else:
                recommendation = classify_variant_recommendation(
                    baseline_total_return=float(baseline_metrics.get("total_return", 0.0)),
                    variant_total_return=float(metrics["total_return"]),
                    baseline_max_drawdown=float(baseline_metrics.get("max_drawdown", 0.0)),
                    variant_max_drawdown=float(metrics["max_drawdown"]),
                )
            rows.append(
                {
                    "top_n": int(top_n),
                    "variant_name": variant_name,
                    **metrics,
                    "risk_flagged_candidate_count": baseline_risk_flagged_count,
                    "excluded_high_risk_count": (
                        max(
                            0,
                            baseline_high_count
                            - _candidate_count_for_level(variant_scores, flags, "high"),
                        )
                        if variant_name == "exclude_high_risk"
                        else 0
                    ),
                    "penalized_candidate_count": (
                        baseline_risk_flagged_count
                        if variant_name == "penalty_high_risk"
                        else 0
                    ),
                    "total_return_delta_vs_baseline": return_delta,
                    "max_drawdown_delta_vs_baseline": drawdown_delta,
                    "recommendation": recommendation,
                }
            )
    return pd.DataFrame(rows).reindex(columns=SUMMARY_COLUMNS)


def format_intraday_risk_filter_report(summary: pd.DataFrame) -> str:
    lines = [
        "# Intraday Risk Filter Backtest",
        "",
        "## Baseline Comparison",
    ]
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

    lines.extend(
        [
            "## Variant Summary",
            summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_intraday_risk_filter_report(
    result: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_path / "intraday_risk_filter_variant_summary.csv",
        "flags": output_path / "intraday_risk_filter_daily_flags.csv",
        "positions": output_path / "intraday_risk_filter_variant_positions.csv",
        "trades": output_path / "intraday_risk_filter_variant_trades.csv",
        "report": output_path / "intraday_risk_filter_report.md",
    }
    result.get("summary", pd.DataFrame()).to_csv(paths["summary"], index=False)
    result.get("flags", pd.DataFrame()).to_csv(paths["flags"], index=False)
    result.get("positions", pd.DataFrame()).to_csv(paths["positions"], index=False)
    result.get("trades", pd.DataFrame()).to_csv(paths["trades"], index=False)
    paths["report"].write_text(
        format_intraday_risk_filter_report(result.get("summary", pd.DataFrame())),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in paths.items()}


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    output_columns = ["trade_date", "asset_id", "rank", "score_total"]
    if scores.empty or any(column not in scores.columns for column in output_columns):
        return pd.DataFrame(columns=output_columns)
    frame = scores.dropna(subset=["trade_date", "asset_id"]).copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    return frame[output_columns].dropna(
        subset=["trade_date", "asset_id", "score_total"]
    )


def _attach_flags(scores: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    if flags.empty:
        result = scores.copy()
        result["intraday_risk_level"] = "none"
        result["intraday_risk_flag_count"] = 0
        return result

    flag_cols = ["trade_date", "asset_id", "intraday_risk_level", "intraday_risk_flag_count"]
    normalized_flags = flags[flag_cols].dropna(subset=["trade_date", "asset_id"]).copy()
    if normalized_flags.empty:
        result = scores.copy()
        result["intraday_risk_level"] = "none"
        result["intraday_risk_flag_count"] = 0
        return result
    normalized_flags["trade_date"] = normalized_flags["trade_date"].astype(str).str[:10]
    normalized_flags["asset_id"] = normalized_flags["asset_id"].astype(str)
    result = scores.merge(normalized_flags, on=["trade_date", "asset_id"], how="left")
    result["intraday_risk_level"] = result["intraday_risk_level"].fillna("none")
    result["intraday_risk_flag_count"] = (
        pd.to_numeric(result["intraday_risk_flag_count"], errors="coerce").fillna(0).astype(int)
    )
    return result


def _rerank_scores(scores: pd.DataFrame) -> pd.DataFrame:
    ranked = scores.sort_values(
        ["trade_date", "score_total", "asset_id"], ascending=[True, False, True]
    ).copy()
    ranked["rank"] = ranked.groupby("trade_date").cumcount() + 1
    return ranked.reset_index(drop=True)


def _tag_frame(frame: pd.DataFrame, top_n: int, variant_name: str) -> pd.DataFrame:
    tagged = frame.copy() if frame is not None else pd.DataFrame()
    tagged["top_n"] = int(top_n)
    tagged["variant_name"] = variant_name
    return tagged


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def _result_metrics(result: Any) -> dict[str, float]:
    summary = dict(getattr(result, "summary", {}) or {})
    equity_curve = getattr(result, "equity_curve", pd.DataFrame())
    trades = getattr(result, "trades", pd.DataFrame())
    final_equity = _metric(summary, "final_equity", None)
    if final_equity is None:
        final_equity = (
            float(equity_curve.iloc[-1]["equity"])
            if not equity_curve.empty and "equity" in equity_curve.columns
            else 1.0 + float(summary.get("total_return", 0.0))
        )
    total_return = _metric(summary, "total_return", float(final_equity) - 1.0)
    annualized_return = _metric(
        summary,
        "annualized_return",
        _annualized_return(equity_curve, total_return),
    )
    annualized_volatility = _metric(
        summary,
        "annualized_volatility",
        _annualized_volatility(equity_curve),
    )
    sharpe_ratio = _metric(
        summary,
        "sharpe_ratio",
        (
            annualized_return / annualized_volatility
            if annualized_volatility and not pd.isna(annualized_volatility)
            else 0.0
        ),
    )
    total_transaction_cost = _metric(summary, "total_transaction_cost", None)
    if total_transaction_cost is None:
        if not equity_curve.empty and "transaction_cost" in equity_curve.columns:
            total_transaction_cost = float(
                pd.to_numeric(equity_curve["transaction_cost"], errors="coerce").fillna(0).sum()
            )
        elif not trades.empty and "transaction_cost" in trades.columns:
            total_transaction_cost = float(
                pd.to_numeric(trades["transaction_cost"], errors="coerce").fillna(0).sum()
            )
        else:
            total_transaction_cost = 0.0
    return {
        "final_equity": float(final_equity),
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "annualized_volatility": float(annualized_volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": _metric(summary, "max_drawdown", _max_drawdown(equity_curve)),
        "average_turnover": _metric(summary, "average_turnover", _average_turnover(equity_curve)),
        "total_transaction_cost": float(total_transaction_cost),
        "average_holdings_count": _average_holdings_count(equity_curve),
        "minimum_holdings_count": _minimum_holdings_count(equity_curve),
    }


def _metric(summary: dict[str, Any], key: str, default: float | None) -> float | None:
    value = summary.get(key, default)
    if value is None or pd.isna(value):
        return default
    return float(value)


def _annualized_return(equity_curve: pd.DataFrame, total_return: float) -> float:
    periods = len(equity_curve) if equity_curve is not None else 0
    if periods <= 0:
        return float(total_return)
    return float((1.0 + total_return) ** (252.0 / periods) - 1.0)


def _annualized_volatility(equity_curve: pd.DataFrame) -> float:
    if equity_curve is None or equity_curve.empty or "net_return" not in equity_curve.columns:
        return 0.0
    returns = pd.to_numeric(equity_curve["net_return"], errors="coerce").dropna()
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * (252.0**0.5))


def _max_drawdown(equity_curve: pd.DataFrame) -> float:
    if equity_curve is None or equity_curve.empty:
        return 0.0
    if "drawdown" in equity_curve.columns:
        return float(pd.to_numeric(equity_curve["drawdown"], errors="coerce").min())
    if "equity" not in equity_curve.columns:
        return 0.0
    equity = pd.to_numeric(equity_curve["equity"], errors="coerce").dropna()
    if equity.empty:
        return 0.0
    return float((equity / equity.cummax() - 1.0).min())


def _average_turnover(equity_curve: pd.DataFrame) -> float:
    if equity_curve is None or equity_curve.empty or "turnover" not in equity_curve.columns:
        return 0.0
    return float(pd.to_numeric(equity_curve["turnover"], errors="coerce").mean())


def _average_holdings_count(equity_curve: pd.DataFrame) -> float:
    if equity_curve is None or equity_curve.empty or "holdings_count" not in equity_curve.columns:
        return 0.0
    return float(pd.to_numeric(equity_curve["holdings_count"], errors="coerce").mean())


def _minimum_holdings_count(equity_curve: pd.DataFrame) -> int:
    if equity_curve is None or equity_curve.empty or "holdings_count" not in equity_curve.columns:
        return 0
    value = pd.to_numeric(equity_curve["holdings_count"], errors="coerce").min()
    return 0 if pd.isna(value) else int(value)


def _scores_with_risk(scores: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    if scores is None or scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "intraday_risk_level"])
    return _attach_flags(_normalize_scores(scores), flags)


def _risk_flagged_candidate_count(scores: pd.DataFrame, flags: pd.DataFrame) -> int:
    flagged = _scores_with_risk(scores, flags)
    if flagged.empty:
        return 0
    return int(flagged["intraday_risk_level"].isin(["watch", "high"]).sum())


def _candidate_count_for_level(scores: pd.DataFrame, flags: pd.DataFrame, level: str) -> int:
    flagged = _scores_with_risk(scores, flags)
    if flagged.empty:
        return 0
    return int(flagged["intraday_risk_level"].eq(level).sum())


def _format_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def _format_number(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2f}"
