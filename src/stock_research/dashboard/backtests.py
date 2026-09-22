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
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard
from stock_research.mid_trend_v1 import run_mid_trend_v1_backtest_for_dashboard
from stock_research.tech_bottleneck_v1 import run_tech_bottleneck_v1_backtest_for_dashboard
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
    strategies = [
        strategy
        for strategy in list_strategy_catalog()
        if strategy["strategy_id"] in BACKTEST_LAB_STRATEGY_IDS and strategy["status"] == "runnable"
    ]
    return _enrich_strategies_with_latest_db_metrics(strategies)


def _enrich_strategies_with_latest_db_metrics(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        with connect(SETTINGS.research_service) as conn:
            return [_with_latest_db_metrics(conn, strategy) for strategy in strategies]
    except Exception:
        return strategies


def _with_latest_db_metrics(conn: Any, strategy: dict[str, Any]) -> dict[str, Any]:
    run_rows = fetch_all(
        conn,
        """
        SELECT run_id, summary_json
        FROM backtest.strategy_backtest_run
        WHERE strategy_id = %s
        ORDER BY end_date DESC, created_at DESC
        LIMIT 1
        """,
        [strategy["strategy_id"]],
    )
    if not run_rows:
        return strategy

    run = run_rows[0]
    equity_rows = fetch_all(
        conn,
        """
        SELECT trade_date::text AS trade_date, equity, drawdown, daily_return
        FROM (
            SELECT DISTINCT ON (trade_date)
                   trade_date, equity, drawdown, daily_return
            FROM backtest.strategy_backtest_equity
            WHERE run_id = %s
            ORDER BY trade_date DESC, row_index DESC
        ) latest_days
        ORDER BY trade_date DESC
        LIMIT 2
        """,
        [run["run_id"]],
    )
    if not equity_rows:
        return strategy

    latest = equity_rows[0]
    previous = equity_rows[1] if len(equity_rows) > 1 else None
    signal_status, signal_count = _latest_position_signal_metrics(conn, str(run["run_id"]))
    summary = run.get("summary_json") if isinstance(run.get("summary_json"), dict) else {}
    metrics = dict(strategy.get("latest_metrics") or {})
    latest_equity = _finite_or_none(latest.get("equity"))
    previous_equity = _finite_or_none(previous.get("equity")) if previous else None
    latest_daily_return = _finite_or_none(latest.get("daily_return"))
    if latest_daily_return is None and latest_equity is not None and previous_equity not in (None, 0.0):
        latest_daily_return = latest_equity / previous_equity - 1.0

    next_strategy = dict(strategy)
    next_strategy["latest_metrics"] = {
        **metrics,
        "as_of_date": str(latest.get("trade_date") or metrics.get("as_of_date") or ""),
        "total_return_pct": _percent_metric(
            summary.get("total_return"),
            fallback=(latest_equity - 1.0 if latest_equity is not None else None),
        ),
        "max_drawdown_pct": _percent_metric(summary.get("max_drawdown"), fallback=_finite_or_none(latest.get("drawdown"))),
        "latest_day_return_pct": _percent_metric(latest_daily_return),
        "latest_day_drawdown_pct": _percent_metric(_finite_or_none(latest.get("drawdown"))),
        "signal_status": signal_status,
        "signal_count": signal_count,
    }
    return next_strategy


def _latest_position_signal_metrics(conn: Any, run_id: str) -> tuple[str, int | None]:
    rows = fetch_all(
        conn,
        """
        WITH latest_position_date AS (
            SELECT MAX(trade_date) AS trade_date
            FROM backtest.strategy_backtest_position
            WHERE run_id = %s
        )
        SELECT COUNT(p.asset_id) AS signal_count
        FROM latest_position_date latest
        LEFT JOIN backtest.strategy_backtest_position p
          ON p.run_id = %s
         AND p.trade_date = latest.trade_date
        """,
        [run_id, run_id],
    )
    count = int(rows[0]["signal_count"] or 0) if rows else 0
    return ("connected", count) if count > 0 else ("no_position_rows", None)


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percent_metric(value: Any, *, fallback: float | None = None) -> float | None:
    number = _finite_or_none(value)
    if number is None:
        number = fallback
    return round(number * 100.0, 2) if number is not None else None


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
    max_position_weight = _optional_position_weight(payload.get("max_position_weight"))
    risk_profile = _optional_text(payload.get("risk_profile"), "balanced")
    rebalance_frequency = _default_rebalance_frequency(strategy_id)
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
        "max_position_weight": max_position_weight,
        "risk_profile": risk_profile,
        "adjust_type": adjust_type,
    }
    vector_config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        max_positions=max_positions,
        max_position_weight=max_position_weight,
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
    if strategy_id == "lhb_shortline":
        result = run_lhb_shortline_v1_backtest_for_dashboard(
            {
                "start_date": params.start_date,
                "end_date": params.end_date,
                **run_config,
            }
        )
        return _with_execution_metadata(
            to_json_safe(result),
            mode="fresh",
            source=str(result.get("source_kind") or "lhb_shortline_v1"),
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    if strategy_id == "mid_trend":
        result = run_mid_trend_v1_backtest_for_dashboard(
            {
                "start_date": params.start_date,
                "end_date": params.end_date,
                **run_config,
            }
        )
        return _with_execution_metadata(
            to_json_safe(result),
            mode="fresh",
            source=str(result.get("source_kind") or "mid_trend_v1"),
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    if strategy_id == "tech_bottleneck":
        result = run_tech_bottleneck_v1_backtest_for_dashboard(
            {
                "start_date": params.start_date,
                "end_date": params.end_date,
                **run_config,
            }
        )
        return _with_execution_metadata(
            to_json_safe(result),
            mode="fresh",
            source=str(result.get("source_kind") or "tech_bottleneck_v1"),
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

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
            "max_position_weight": config.max_position_weight,
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


def _optional_position_weight(value: Any) -> float | None:
    if value is None or value == "":
        return None
    parsed = _finite_float(value, "max_position_weight", 0.0)
    if parsed > 1:
        parsed = parsed / 100.0
    if not (0 < parsed <= 1):
        raise ValueError("max_position_weight must be greater than 0 and at most 100%")
    return parsed


def _rebalance_frequency(value: Any) -> str:
    frequency = _optional_text(value, "weekly")
    if frequency not in {"daily", "weekly"}:
        raise ValueError("rebalance_frequency must be daily or weekly")
    return frequency


def _default_rebalance_frequency(strategy_id: str) -> str:
    if strategy_id == "lhb_shortline":
        return "daily"
    return "weekly"


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
