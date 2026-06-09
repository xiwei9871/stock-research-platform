import math
from numbers import Integral, Real
from typing import Any

import pandas as pd

from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    load_vectorized_topn_inputs,
    run_vectorized_topn_backtest,
)

RUNNABLE_STRATEGY_ID = "manual_v1_topn_rotation"


def list_backtest_strategies() -> list[dict[str, Any]]:
    return list_strategy_catalog()


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = _required_text(payload, "strategy_id")
    if strategy_id != RUNNABLE_STRATEGY_ID:
        raise ValueError("only manual_v1_topn_rotation is runnable in this version")

    start_date = _required_text(payload, "start_date")
    end_date = _required_text(payload, "end_date")
    score_version = _optional_text(payload.get("score_version"), "manual_v1")
    adjust_type = _optional_text(payload.get("adjust_type"), "hfq")
    top_n = _positive_int(payload.get("top_n"), "top_n", 20)
    max_positions = _optional_positive_int(payload.get("max_positions"), "max_positions")
    rebalance_frequency = _rebalance_frequency(payload.get("rebalance_frequency"))
    transaction_cost_bps = _finite_float(
        payload.get("transaction_cost_bps"),
        "transaction_cost_bps",
        0.0,
    )

    scores, prices = load_vectorized_topn_inputs(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        adjust_type=adjust_type,
    )
    config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        max_positions=max_positions,
    )
    result = run_vectorized_topn_backtest(scores, prices, config)

    return {
        "strategy_id": strategy_id,
        "strategy_name": _strategy_name(strategy_id),
        "read_only": True,
        "config": {
            "start_date": start_date,
            "end_date": end_date,
            "score_version": score_version,
            "top_n": config.top_n,
            "rebalance_frequency": config.rebalance_frequency,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_positions": config.max_positions,
            "adjust_type": adjust_type,
        },
        "summary": to_json_safe(result.summary),
        "equity_curve": _frame_records(result.equity_curve),
        "positions": _frame_records(result.positions),
        "trades": _frame_records(result.trades),
    }


def to_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, pd.Series | pd.Index):
        return [to_json_safe(item) for item in value.to_list()]
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.time() == pd.Timestamp(value.date()).time():
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            return None
        return numeric_value
    if isinstance(value, str):
        return value
    return str(value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None or value == "":
        raise ValueError(f"{field} is required")
    return str(value)


def _optional_text(value: Any, default: str) -> str:
    if value is None or value == "":
        return default
    return str(value)


def _positive_int(value: Any, field: str, default: int) -> int:
    if value is None or value == "":
        value = default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    return _positive_int(value, field, 0)


def _finite_float(value: Any, field: str, default: float) -> float:
    if value is None or value == "":
        value = default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _rebalance_frequency(value: Any) -> str:
    frequency = _optional_text(value, "weekly")
    if frequency not in {"daily", "weekly"}:
        raise ValueError("rebalance_frequency must be daily or weekly")
    return frequency


def _frame_records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [to_json_safe(row) for row in frame.to_dict("records")]


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _strategy_name(strategy_id: str) -> str:
    for row in list_strategy_catalog():
        if row["strategy_id"] == strategy_id:
            return str(row["strategy_name"])
    return strategy_id
