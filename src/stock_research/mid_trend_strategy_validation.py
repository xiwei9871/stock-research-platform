from __future__ import annotations

import pandas as pd

SEVERE_DRAWDOWN_THRESHOLD = 0.20


def discover_mid_trend_strategy_candidates() -> list[dict[str, object]]:
    return [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "runner_name": "run_current_mid_trend_strategy_v1_backtest",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_shadow_backtest",
            "group": "portfolio",
            "runner_name": "run_mid_trend_shadow_backtest",
            "result_keys": {"positions", "trades", "equity_curve", "summary"},
        },
    ]


def filter_complete_mid_trend_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    complete: list[dict[str, object]] = []
    for candidate in candidates:
        result_keys = set(candidate.get("result_keys", set()))
        if {"trades", "summary"} - result_keys:
            continue
        if not (
            {"holdings", "equity"} <= result_keys
            or {"positions", "equity_curve"} <= result_keys
        ):
            continue
        if candidate.get("group") != "portfolio":
            continue
        complete.append(candidate)
    return complete


def _normalize_mid_trend_validation_result(item: dict[str, object]) -> dict[str, object]:
    strategy_id = str(item["strategy_id"])
    if "summary_frame" in item and "equity_frame" in item:
        return {
            "strategy_id": strategy_id,
            "summary_frame": _normalize_summary_frame(item["summary_frame"]),
            "equity_frame": _normalize_equity_frame(item["equity_frame"]),
        }

    summary = item.get("summary")
    if not isinstance(summary, pd.DataFrame):
        raise ValueError(f"{strategy_id} is missing a DataFrame summary payload")

    if strategy_id == "current_mid_trend_strategy_v1":
        equity = item.get("equity")
        if not isinstance(equity, pd.DataFrame):
            raise ValueError(f"{strategy_id} is missing a DataFrame equity payload")
        return {
            "strategy_id": strategy_id,
            "summary_frame": _wide_summary_to_metric_frame(summary, strategy_id),
            "equity_frame": _normalize_equity_frame(equity),
        }

    if strategy_id == "mid_trend_shadow_backtest":
        equity_curve = item.get("equity_curve")
        if not isinstance(equity_curve, pd.DataFrame):
            raise ValueError(f"{strategy_id} is missing a DataFrame equity_curve payload")
        return {
            "strategy_id": strategy_id,
            "summary_frame": _normalize_summary_frame(summary),
            "equity_frame": _normalize_equity_frame(equity_curve),
        }

    raise ValueError(f"Unsupported mid-trend validation strategy output: {strategy_id}")


def build_mid_trend_validation_scorecard(results: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in results:
        normalized = _normalize_mid_trend_validation_result(item)
        summary = normalized["summary_frame"]
        summary_map = _numeric_summary_map(summary)
        equity = normalized["equity_frame"].copy()
        equity["date"] = pd.to_datetime(equity["date"])
        equity["month"] = equity["date"].dt.to_period("M")
        monthly_equity = equity.groupby("month")["equity"].last().pct_change().dropna()
        total_return = summary_map.get("total_return", float("nan"))
        max_drawdown = summary_map.get("max_drawdown", float("nan"))
        average_turnover = summary_map.get("average_turnover", float("nan"))
        monthly_win_rate = (
            float((monthly_equity > 0).mean()) if len(monthly_equity) else float("nan")
        )
        rows.append(
            {
                "strategy_id": normalized["strategy_id"],
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "return_drawdown_ratio": (
                    total_return / abs(max_drawdown)
                    if max_drawdown < 0
                    else float("inf")
                    if max_drawdown == 0 and total_return > 0
                    else float("nan")
                ),
                "monthly_win_rate": monthly_win_rate,
                "turnover_penalized_stability": _turnover_penalized_stability(
                    monthly_win_rate,
                    average_turnover,
                ),
            }
        )
    return pd.DataFrame(rows)


def rank_mid_trend_validation_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    ranked = scorecard.copy()
    ranked["drawdown_penalty"] = ranked["max_drawdown"].abs()
    # Treat clearly bad drawdown as a coarse filter, then rank on efficiency and stability.
    ranked["severe_drawdown"] = ranked["drawdown_penalty"] > SEVERE_DRAWDOWN_THRESHOLD
    return ranked.sort_values(
        [
            "severe_drawdown",
            "return_drawdown_ratio",
            "monthly_win_rate",
            "turnover_penalized_stability",
            "drawdown_penalty",
            "total_return",
        ],
        ascending=[True, False, False, False, True, False],
    ).reset_index(drop=True)


def _normalize_summary_frame(summary: object) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame):
        raise ValueError("summary_frame must be a pandas DataFrame")
    if {"metric", "value"} <= set(summary.columns):
        return summary.loc[:, ["metric", "value"]].copy()
    return _wide_summary_to_metric_frame(summary)


def _wide_summary_to_metric_frame(summary: pd.DataFrame, strategy_id: str | None = None) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=["metric", "value"])

    row = summary.iloc[0]
    if strategy_id and "strategy_family" in summary.columns:
        matched = summary[summary["strategy_family"].astype(str) == strategy_id]
        if not matched.empty:
            row = matched.iloc[0]
    records = [{"metric": str(column), "value": row[column]} for column in summary.columns]
    return pd.DataFrame(records, columns=["metric", "value"])


def _normalize_equity_frame(equity: object) -> pd.DataFrame:
    if not isinstance(equity, pd.DataFrame):
        raise ValueError("equity_frame must be a pandas DataFrame")
    frame = equity.copy()
    if "date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "date"})
    return frame


def _numeric_summary_map(summary: pd.DataFrame) -> dict[str, float]:
    summary_frame = summary.copy()
    summary_frame["metric"] = summary_frame["metric"].astype(str)
    summary_frame["numeric_value"] = pd.to_numeric(summary_frame["value"], errors="coerce")
    numeric_rows = summary_frame.dropna(subset=["numeric_value"])
    return {
        row["metric"]: float(row["numeric_value"])
        for row in numeric_rows.to_dict("records")
    }


def _turnover_penalized_stability(
    monthly_win_rate: float,
    average_turnover: float,
) -> float:
    if pd.isna(monthly_win_rate) or pd.isna(average_turnover):
        return float("nan")
    turnover = min(max(float(average_turnover), 0.0), 1.0)
    return (1.0 - turnover) * float(monthly_win_rate)
