from __future__ import annotations

import datetime as dt
import json
import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def replay_payload_to_read_model_rows(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = _required_text(payload, "strategy_id")
    strategy_name = _required_text(payload, "strategy_name")
    config = _dict_value(payload.get("config"))
    summary = _dict_value(payload.get("summary"))
    combo_scheme = str(summary.get("combo_scheme") or f"{strategy_id}_combo_v1")
    start_date = _required_text(config, "start_date")
    end_date = _required_text(config, "end_date")
    run_id = str(payload.get("run_id") or f"{strategy_id}:{combo_scheme}:{start_date}:{end_date}")

    return {
        "run": {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "combo_scheme": combo_scheme,
            "start_date": start_date,
            "end_date": end_date,
            "summary_json": _json_ready(summary),
            "config_json": _json_ready(config),
            "source_kind": str(payload.get("source_kind") or "validated_combo_replay"),
            "source_paths": _json_ready(payload.get("source_paths") or []),
        },
        "equity": [
            _child_row(
                row,
                run_id=run_id,
                row_index=index,
                date_keys=("date", "trade_date"),
                numeric_keys={
                    "equity": ("equity",),
                    "drawdown": ("drawdown",),
                    "daily_return": ("daily_return", "net_return", "gross_return"),
                    "turnover": ("turnover",),
                    "invested_weight": ("invested_weight",),
                },
            )
            for index, row in enumerate(_list_of_dicts(payload.get("equity_curve")))
        ],
        "positions": [
            _child_row(
                row,
                run_id=run_id,
                row_index=index,
                date_keys=("rebalance_date", "trade_date", "date"),
                text_keys={"asset_id": ("asset_id",)},
                numeric_keys={"weight": ("weight", "target_weight"), "rank": ("rank", "score_rank")},
            )
            for index, row in enumerate(_list_of_dicts(payload.get("positions")))
        ],
        "trades": [
            _child_row(
                row,
                run_id=run_id,
                row_index=index,
                date_keys=("trade_date", "execution_date", "date"),
                text_keys={"asset_id": ("asset_id",), "side": ("side", "action")},
                numeric_keys={
                    "weight": ("weight", "target_weight", "executed_weight", "delta_weight"),
                    "realized_return": ("realized_return", "return", "pnl"),
                },
            )
            for index, row in enumerate(_list_of_dicts(payload.get("trades")))
        ],
    }


def import_strategy_backtest_replay_payload(
    payload: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = replay_payload_to_read_model_rows(payload)
    run_id = rows["run"]["run_id"]
    with connect(service) as conn:
        with conn.cursor() as cur:
            _upsert_run(cur, rows["run"])
            _replace_child_rows(cur, "equity", run_id, rows["equity"])
            _replace_child_rows(cur, "position", run_id, rows["positions"])
            _replace_child_rows(cur, "trade", run_id, rows["trades"])
    return {
        "run_id": run_id,
        "equity_rows": len(rows["equity"]),
        "position_rows": len(rows["positions"]),
        "trade_rows": len(rows["trades"]),
    }


def load_strategy_backtest_replay_payload(
    strategy_id: str,
    *,
    start_date: str,
    end_date: str,
    combo_scheme: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    run_filters = [strategy_id, start_date, end_date]
    combo_clause = ""
    if combo_scheme:
        combo_clause = " AND combo_scheme = %s"
        run_filters.append(combo_scheme)
    with connect(service) as conn:
        runs = fetch_all(
            conn,
            f"""
            SELECT run_id, strategy_id, strategy_name, combo_scheme, start_date::text AS start_date,
                   end_date::text AS end_date, summary_json, config_json
            FROM backtest.strategy_backtest_run
            WHERE strategy_id = %s
              AND start_date = %s
              AND end_date = %s
              {combo_clause}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            run_filters,
        )
        if not runs:
            return None
        run = runs[0]
        run_id = str(run["run_id"])
        equity = _load_child_rows(conn, "equity", run_id)
        positions = _load_child_rows(conn, "position", run_id)
        trades = _load_child_rows(conn, "trade", run_id)
    return normalize_replay_payload_to_requested_window({
        "strategy_id": str(run["strategy_id"]),
        "strategy_name": str(run["strategy_name"]),
        "read_only": True,
        "config": _json_object(run.get("config_json")),
        "summary": _json_object(run.get("summary_json")),
        "equity_curve": equity,
        "positions": positions,
        "trades": trades,
    })


def normalize_replay_payload_to_requested_window(payload: dict[str, Any]) -> dict[str, Any]:
    config = _json_object(payload.get("config"))
    start_date = str(config.get("start_date") or "")
    end_date = str(config.get("end_date") or "")
    if not start_date or not end_date:
        return payload

    scoped = dict(payload)
    scoped["config"] = config
    scoped["equity_curve"] = _rebase_equity_rows(
        _filter_rows_by_date(_list_of_dicts(payload.get("equity_curve")), start_date, end_date, ("date", "trade_date"))
    )
    scoped["positions"] = _filter_rows_by_date(
        _list_of_dicts(payload.get("positions")),
        start_date,
        end_date,
        ("rebalance_date", "trade_date", "date"),
    )
    scoped["trades"] = _filter_rows_by_date(
        _list_of_dicts(payload.get("trades")),
        start_date,
        end_date,
        ("trade_date", "execution_date", "date", "entry_trade_date", "exit_trade_date"),
    )
    scoped["summary"] = _summary_for_requested_window(
        _json_object(payload.get("summary")),
        config=config,
        equity=scoped["equity_curve"],
        positions=scoped["positions"],
        trades=scoped["trades"],
    )
    return scoped


def _filter_rows_by_date(
    rows: list[dict[str, Any]],
    start_date: str,
    end_date: str,
    date_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    for row in rows:
        row_date = _row_date(row, date_keys)
        if row_date is None or start is None or end is None or (start <= row_date <= end):
            filtered.append(dict(row))
    return filtered


def _rebase_equity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    equity_values = [_float_value(row.get("equity")) for row in rows]
    base = next((value for value in equity_values if value is not None and value != 0.0), None)
    if base is None:
        return rows

    rebased: list[dict[str, Any]] = []
    high_water: float | None = None
    previous_equity: float | None = None
    for row, original_equity in zip(rows, equity_values, strict=False):
        next_row = dict(row)
        if original_equity is not None:
            equity = original_equity / base
            high_water = equity if high_water is None else max(high_water, equity)
            next_row["equity"] = _rounded_float(equity)
            for component_key in ("cash", "invested_notional", "position_notional", "daily_realized_pnl"):
                component_value = _float_value(next_row.get(component_key))
                if component_value is not None:
                    next_row[component_key] = _rounded_float(component_value / base)
            next_row["drawdown"] = _rounded_float(equity / high_water - 1.0 if high_water else 0.0)
            daily_return = 0.0 if previous_equity is None else equity / previous_equity - 1.0
            if "daily_return" in next_row:
                next_row["daily_return"] = _rounded_float(daily_return)
            if "net_return" in next_row:
                next_row["net_return"] = _rounded_float(daily_return)
            previous_equity = equity
        rebased.append(next_row)
    return rebased


def _summary_for_requested_window(
    summary: dict[str, Any],
    *,
    config: dict[str, Any],
    equity: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(summary)
    start_date = str(config.get("start_date") or "")
    end_date = str(config.get("end_date") or "")
    result["start_date"] = start_date
    result["end_date"] = end_date
    result["requested_start_date"] = start_date
    result["requested_end_date"] = end_date
    result["position_rows"] = len(positions)
    result["trade_rows"] = len(trades)

    dated_equity = [(row, _row_date(row, ("date", "trade_date"))) for row in equity]
    dated_equity = [(row, date) for row, date in dated_equity if date is not None]
    if not dated_equity:
        result["periods"] = 0
        return result

    result["actual_start_date"] = dated_equity[0][1].isoformat()
    result["actual_end_date"] = dated_equity[-1][1].isoformat()
    result["periods"] = len(equity)
    equity_values = [_float_value(row.get("equity")) for row in equity]
    equity_values = [value for value in equity_values if value is not None]
    if equity_values:
        final_equity = equity_values[-1]
        result["final_equity"] = _rounded_float(final_equity)
        result["total_return"] = _rounded_float(final_equity - 1.0)
        high_water = equity_values[0]
        max_drawdown = 0.0
        for value in equity_values:
            high_water = max(high_water, value)
            max_drawdown = min(max_drawdown, value / high_water - 1.0 if high_water else 0.0)
        result["max_drawdown"] = _rounded_float(max_drawdown)
    return result


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO backtest.strategy_backtest_run (
            run_id, strategy_id, strategy_name, combo_scheme, start_date, end_date,
            summary_json, config_json, source_kind, source_paths
        )
        VALUES (
            %(run_id)s, %(strategy_id)s, %(strategy_name)s, %(combo_scheme)s,
            %(start_date)s, %(end_date)s, %(summary_json)s::jsonb,
            %(config_json)s::jsonb, %(source_kind)s, %(source_paths)s::jsonb
        )
        ON CONFLICT (run_id)
        DO UPDATE SET
            strategy_id = EXCLUDED.strategy_id,
            strategy_name = EXCLUDED.strategy_name,
            combo_scheme = EXCLUDED.combo_scheme,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            summary_json = EXCLUDED.summary_json,
            config_json = EXCLUDED.config_json,
            source_kind = EXCLUDED.source_kind,
            source_paths = EXCLUDED.source_paths,
            updated_at = now()
        """,
        {
            **row,
            "summary_json": json.dumps(row["summary_json"], sort_keys=True),
            "config_json": json.dumps(row["config_json"], sort_keys=True),
            "source_paths": json.dumps(row["source_paths"], sort_keys=True),
        },
    )


def _replace_child_rows(cur: Any, child: str, run_id: str, rows: list[dict[str, Any]]) -> None:
    table = f"backtest.strategy_backtest_{child}"
    cur.execute(f"DELETE FROM {table} WHERE run_id = %s", [run_id])
    for row in rows:
        if child == "equity":
            _insert_equity(cur, row)
        elif child == "position":
            _insert_position(cur, row)
        elif child == "trade":
            _insert_trade(cur, row)
        else:
            raise ValueError(f"unsupported child table: {child}")


def _insert_equity(cur: Any, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO backtest.strategy_backtest_equity (
            run_id, trade_date, row_index, equity, drawdown, daily_return,
            turnover, invested_weight, row_json
        )
        VALUES (
            %(run_id)s, %(trade_date)s, %(row_index)s, %(equity)s,
            %(drawdown)s, %(daily_return)s, %(turnover)s,
            %(invested_weight)s, %(row_json)s::jsonb
        )
        """,
        _json_param_row(row),
    )


def _insert_position(cur: Any, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO backtest.strategy_backtest_position (
            run_id, trade_date, row_index, asset_id, weight, rank, row_json
        )
        VALUES (
            %(run_id)s, %(trade_date)s, %(row_index)s, %(asset_id)s,
            %(weight)s, %(rank)s, %(row_json)s::jsonb
        )
        """,
        _json_param_row(row),
    )


def _insert_trade(cur: Any, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO backtest.strategy_backtest_trade (
            run_id, trade_date, row_index, asset_id, side, weight, realized_return, row_json
        )
        VALUES (
            %(run_id)s, %(trade_date)s, %(row_index)s, %(asset_id)s, %(side)s,
            %(weight)s, %(realized_return)s, %(row_json)s::jsonb
        )
        """,
        _json_param_row(row),
    )


def _load_child_rows(conn: Any, child: str, run_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        conn,
        f"""
        SELECT row_json
        FROM backtest.strategy_backtest_{child}
        WHERE run_id = %s
        ORDER BY trade_date, row_index
        """,
        [run_id],
    )
    return [_json_object(row["row_json"]) for row in rows]


def _child_row(
    row: dict[str, Any],
    *,
    run_id: str,
    row_index: int,
    date_keys: tuple[str, ...],
    text_keys: dict[str, tuple[str, ...]] | None = None,
    numeric_keys: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "run_id": run_id,
        "trade_date": _date_value(row, date_keys),
        "row_index": row_index,
        "row_json": _json_ready(row),
    }
    for target, keys in (text_keys or {}).items():
        result[target] = _text_value(row, keys)
    for target, keys in (numeric_keys or {}).items():
        result[target] = _numeric_value(row, keys)
    return result


def _date_value(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)[:10]
    raise ValueError(f"missing date column in replay row: {keys}")


def _row_date(row: dict[str, Any], keys: tuple[str, ...]) -> dt.date | None:
    for key in keys:
        value = row.get(key)
        parsed = _parse_date(value)
        if parsed is not None:
            return parsed
    return None


def _parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _rounded_float(value: float) -> float:
    return round(float(value), 10)


def _text_value(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _numeric_value(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def _json_param_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "row_json": json.dumps(row["row_json"], sort_keys=True),
    }


def _required_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if value in (None, ""):
        raise ValueError(f"required_field_missing: {key}")
    return str(value)


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items() if _json_ready(item) is not None}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            return _json_ready(value.item())
    except (ImportError, TypeError, ValueError):
        pass
    return value
