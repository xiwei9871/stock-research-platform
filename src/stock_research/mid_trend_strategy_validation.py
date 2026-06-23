from __future__ import annotations


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
