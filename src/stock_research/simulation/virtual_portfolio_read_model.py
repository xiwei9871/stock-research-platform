from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_virtual_portfolio_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"virtual portfolio review must be a JSON object: {json_path}")

    portfolio_id = str(review.get("portfolio_id") or "")
    if not portfolio_id:
        raise ValueError(f"virtual portfolio review requires portfolio_id: {json_path}")
    review_status = str(review.get("status") or "")
    auto_trade_enabled = bool(review.get("auto_trade_enabled"))
    human_confirmation_required = bool(review.get("human_confirmation_required", True))

    states = [
        _state_row(
            row,
            portfolio_id=portfolio_id,
            review_status=review_status,
            auto_trade_enabled=auto_trade_enabled,
            human_confirmation_required=human_confirmation_required,
            fallback_source_path=json_path,
        )
        for row in review.get("history_rows", [])
        if isinstance(row, dict)
    ]
    positions = [
        _position_row(row, portfolio_id=portfolio_id, source_path=json_path)
        for row in review.get("latest_positions", [])
        if isinstance(row, dict)
    ]
    return {"states": states, "positions": positions}


def import_virtual_portfolio_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _review_paths(input_path)
    portfolio_ids: list[str] = []
    state_count = 0
    position_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for review_path in paths:
                rows = load_virtual_portfolio_read_model_rows(review_path)
                for state in rows["states"]:
                    _upsert_state(cur, state)
                    state_count += 1
                for position in rows["positions"]:
                    _upsert_position(cur, position)
                    position_count += 1
                portfolio_ids.extend(
                    sorted({str(row["portfolio_id"]) for row in rows["states"]})
                )
    return {
        "imported_count": len(paths),
        "state_count": state_count,
        "position_count": position_count,
        "portfolio_ids": portfolio_ids,
    }


def _review_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("virtual_portfolio_review_*.json"))
    return [path]


def _upsert_state(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO simulation.virtual_portfolio_state_daily (
        portfolio_id, trade_date, strategy_id, review_status, cash, market_value,
        equity, drawdown, exposure_pct, open_position_count, risk_level,
        auto_trade_enabled, human_confirmation_required, source_artifact_path
    )
    VALUES (
        %(portfolio_id)s, %(trade_date)s, %(strategy_id)s, %(review_status)s,
        %(cash)s, %(market_value)s, %(equity)s, %(drawdown)s, %(exposure_pct)s,
        %(open_position_count)s, %(risk_level)s, %(auto_trade_enabled)s,
        %(human_confirmation_required)s, %(source_artifact_path)s
    )
    ON CONFLICT (portfolio_id, trade_date, strategy_id)
    DO UPDATE SET
        review_status = EXCLUDED.review_status,
        cash = EXCLUDED.cash,
        market_value = EXCLUDED.market_value,
        equity = EXCLUDED.equity,
        drawdown = EXCLUDED.drawdown,
        exposure_pct = EXCLUDED.exposure_pct,
        open_position_count = EXCLUDED.open_position_count,
        risk_level = EXCLUDED.risk_level,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        human_confirmation_required = EXCLUDED.human_confirmation_required,
        source_artifact_path = EXCLUDED.source_artifact_path,
        updated_at = now()
    """
    cur.execute(sql, row)


def _upsert_position(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO simulation.virtual_portfolio_position_daily (
        portfolio_id, trade_date, strategy_id, asset_id, stock_code, stock_name,
        quantity, market_value, weight, cost_basis, unrealized_pnl, source_artifact_path
    )
    VALUES (
        %(portfolio_id)s, %(trade_date)s, %(strategy_id)s, %(asset_id)s,
        %(stock_code)s, %(stock_name)s, %(quantity)s, %(market_value)s,
        %(weight)s, %(cost_basis)s, %(unrealized_pnl)s, %(source_artifact_path)s
    )
    ON CONFLICT (portfolio_id, trade_date, strategy_id, stock_code)
    DO UPDATE SET
        asset_id = EXCLUDED.asset_id,
        stock_name = EXCLUDED.stock_name,
        quantity = EXCLUDED.quantity,
        market_value = EXCLUDED.market_value,
        weight = EXCLUDED.weight,
        cost_basis = EXCLUDED.cost_basis,
        unrealized_pnl = EXCLUDED.unrealized_pnl,
        source_artifact_path = EXCLUDED.source_artifact_path,
        updated_at = now()
    """
    cur.execute(sql, row)


def _state_row(
    row: dict[str, Any],
    *,
    portfolio_id: str,
    review_status: str,
    auto_trade_enabled: bool,
    human_confirmation_required: bool,
    fallback_source_path: Path,
) -> dict[str, Any]:
    return {
        "portfolio_id": portfolio_id,
        "trade_date": str(row.get("trade_date") or ""),
        "strategy_id": str(row.get("strategy_id") or ""),
        "review_status": review_status,
        "cash": row.get("cash"),
        "market_value": row.get("market_value"),
        "equity": row.get("equity"),
        "drawdown": row.get("drawdown"),
        "exposure_pct": row.get("exposure_pct"),
        "open_position_count": int(row.get("open_position_count") or 0),
        "risk_level": row.get("risk_level"),
        "auto_trade_enabled": auto_trade_enabled,
        "human_confirmation_required": human_confirmation_required,
        "source_artifact_path": str(
            row.get("source_artifact_path") or fallback_source_path
        ),
    }


def _position_row(
    row: dict[str, Any],
    *,
    portfolio_id: str,
    source_path: Path,
) -> dict[str, Any]:
    return {
        "portfolio_id": portfolio_id,
        "trade_date": str(row.get("trade_date") or ""),
        "strategy_id": str(row.get("strategy_id") or ""),
        "asset_id": row.get("asset_id"),
        "stock_code": str(row.get("stock_code") or row.get("asset_id") or ""),
        "stock_name": row.get("stock_name"),
        "quantity": row.get("quantity"),
        "market_value": row.get("market_value"),
        "weight": row.get("weight")
        if row.get("weight") is not None
        else row.get("position_weight"),
        "cost_basis": row.get("cost_basis"),
        "unrealized_pnl": row.get("unrealized_pnl"),
        "source_artifact_path": str(source_path),
    }
