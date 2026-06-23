from __future__ import annotations

import pandas as pd


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


def build_mid_trend_validation_scorecard(results: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in results:
        summary = item["summary_frame"]
        summary_map = {
            str(row["metric"]): float(row["value"])
            for row in summary.to_dict("records")
        }
        equity = item["equity_frame"].copy()
        equity["date"] = pd.to_datetime(equity["date"])
        equity["month"] = equity["date"].dt.to_period("M")
        monthly_equity = equity.groupby("month")["equity"].last().pct_change().dropna()
        total_return = summary_map.get("total_return", 0.0)
        max_drawdown = summary_map.get("max_drawdown", 0.0)
        average_turnover = summary_map.get("average_turnover", 0.0)
        monthly_win_rate = (
            float((monthly_equity > 0).mean()) if len(monthly_equity) else float("nan")
        )
        rows.append(
            {
                "strategy_id": item["strategy_id"],
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "return_drawdown_ratio": (
                    total_return / abs(max_drawdown)
                    if max_drawdown < 0
                    else float("nan")
                ),
                "monthly_win_rate": monthly_win_rate,
                "turnover_penalized_stability": (
                    1.0 - min(max(float(average_turnover), 0.0), 1.0)
                ) * (monthly_win_rate if monthly_win_rate == monthly_win_rate else 0.0),
            }
        )
    return pd.DataFrame(rows)


def rank_mid_trend_validation_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    ranked = scorecard.copy()
    ranked["drawdown_penalty"] = ranked["max_drawdown"].abs()
    return ranked.sort_values(
        [
            "drawdown_penalty",
            "return_drawdown_ratio",
            "monthly_win_rate",
            "turnover_penalized_stability",
            "total_return",
        ],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)
