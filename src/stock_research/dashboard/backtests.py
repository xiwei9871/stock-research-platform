import math
import time
from datetime import datetime, timezone
from numbers import Integral, Real
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
)
from stock_research.db import connect, fetch_all
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)

BACKTEST_LAB_STRATEGY_IDS = {
    "lhb_shortline",
    "mid_trend",
    "tech_bottleneck",
}


def list_backtest_strategies() -> list[dict[str, Any]]:
    return [
        strategy
        for strategy in list_strategy_catalog()
        if strategy["strategy_id"] in BACKTEST_LAB_STRATEGY_IDS and strategy["status"] == "runnable"
    ]


def load_vectorized_topn_prices(start_date: str, end_date: str, adjust_type: str) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, open, close, amount, trade_status,
           false AS is_limit_up,
           false AS is_limit_down,
           trade_status <> '1' AS is_suspended
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return pd.DataFrame(rows)


def _parse_backtest_request(
    payload: dict[str, Any],
) -> tuple[str, StrategyBacktestParams, dict[str, Any], VectorizedTopNConfig]:
    strategy_id = _required_text(payload, "strategy_id")
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

    params = StrategyBacktestParams(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        adjust_type=adjust_type,
    )
    run_config = {
        "score_version": score_version,
        "top_n": top_n,
        "rebalance_frequency": rebalance_frequency,
        "transaction_cost_bps": transaction_cost_bps,
        "max_positions": max_positions,
        "adjust_type": adjust_type,
    }
    vector_config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        max_positions=max_positions,
    )
    return strategy_id, params, run_config, vector_config


def _with_execution_metadata(
    payload: dict[str, Any],
    *,
    mode: str,
    source: str,
    started_at: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    result = dict(payload)
    result["execution_mode"] = mode
    result["result_source"] = source
    result["run_started_at"] = started_at
    result["run_finished_at"] = datetime.now(timezone.utc).isoformat()
    result["elapsed_ms"] = round(float(elapsed_ms), 3)
    summary = dict(result.get("summary") or {})
    summary["execution_mode"] = mode
    summary["result_source"] = source
    summary["elapsed_ms"] = result["elapsed_ms"]
    result["summary"] = summary
    return result


def run_replay_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, _vector_config = _parse_backtest_request(payload)
    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")
    replay_runner = getattr(adapter, "run_replay", None)
    if not callable(replay_runner):
        raise ValueError(f"strategy does not support replay: {strategy_id}")
    result = to_json_safe(replay_runner(params, run_config))
    return _with_execution_metadata(
        result,
        mode="replay",
        source=str(result.get("source_kind") or "database_replay"),
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_fresh_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, config = _parse_backtest_request(payload)
    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")

    scores = adapter.load_scores(params)
    prices = load_vectorized_topn_prices(
        start_date=params.start_date,
        end_date=params.end_date,
        adjust_type=params.adjust_type,
    )
    result = run_vectorized_topn_backtest(scores, prices, config)

    payload_result = {
        "strategy_id": strategy_id,
        "strategy_name": _strategy_name(strategy_id),
        "read_only": False,
        "config": {
            "start_date": params.start_date,
            "end_date": params.end_date,
            "score_version": params.score_version,
            "top_n": config.top_n,
            "rebalance_frequency": config.rebalance_frequency,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_positions": config.max_positions,
            "adjust_type": params.adjust_type,
        },
        "summary": {
            **to_json_safe(result.summary),
            "fresh_engine_note": "live score rebuild from selected strategy factors and market prices",
        },
        "equity_curve": _frame_records(result.equity_curve),
        "positions": _frame_records(result.positions),
        "trades": _frame_records(result.trades),
    }
    return _with_execution_metadata(
        payload_result,
        mode="fresh",
        source="live_vectorized_backtest",
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    return run_replay_backtest(payload)


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
