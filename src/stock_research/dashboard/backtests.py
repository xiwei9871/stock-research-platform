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
    strategy_id = str(payload["strategy_id"])
    if strategy_id != RUNNABLE_STRATEGY_ID:
        raise ValueError("only manual_v1_topn_rotation is runnable in this version")

    start_date = str(payload["start_date"])
    end_date = str(payload["end_date"])
    score_version = str(payload.get("score_version") or "manual_v1")
    adjust_type = str(payload.get("adjust_type") or "hfq")

    scores, prices = load_vectorized_topn_inputs(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        adjust_type=adjust_type,
    )
    config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=int(payload.get("top_n") or 20),
        rebalance_frequency=str(payload.get("rebalance_frequency") or "weekly"),
        transaction_cost_bps=float(payload.get("transaction_cost_bps") or 0.0),
        max_positions=_optional_int(payload.get("max_positions")),
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


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


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
