from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from stock_research.portfolio_backtest import PortfolioResult


WARNING_DRAWDOWN = -0.10
BLOCK_DRAWDOWN = -0.20


def build_portfolio_simulation_state(
    result: PortfolioResult,
    *,
    source_run_card_path: str | None = None,
) -> dict[str, Any]:
    latest = _latest_equity_row(result.equity_curve)
    equity = _float_value(latest.get("equity"), default=float(result.config.initial_cash))
    market_value = _float_value(latest.get("market_value"), default=0.0)
    drawdown = _float_value(latest.get("drawdown"), default=0.0)
    positions = _open_positions(result.trades, equity=equity)
    return {
        "trade_date": str(latest.get("date", result.config.end_date)),
        "strategy_id": result.config.strategy_id,
        "start_date": str(result.config.start_date),
        "end_date": str(result.config.end_date),
        "top_k": int(result.config.top_k),
        "holding_days": int(result.config.holding_days),
        "initial_cash": float(result.config.initial_cash),
        "cash": _float_value(latest.get("cash"), default=0.0),
        "market_value": market_value,
        "equity": equity,
        "drawdown": drawdown,
        "exposure_pct": market_value / equity if equity else 0.0,
        "open_position_count": len(positions),
        "positions": positions,
        "risk_level": _risk_level(drawdown),
        "source": "portfolio_backtest",
        "source_run_card_path": source_run_card_path,
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }


def write_portfolio_simulation_state(
    state: dict[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    trade_date = str(state.get("trade_date", "unknown"))
    strategy = _safe_stem(str(state.get("strategy_id", "portfolio")))
    stem = f"portfolio_simulation_state_{trade_date}_{strategy}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    positions_csv_path = output_path / f"{stem}_positions.csv"

    json_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(state.get("positions", [])).to_csv(positions_csv_path, index=False)
    markdown_path.write_text(_render_state_markdown(state, positions_csv_path), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "positions_csv_path": str(positions_csv_path),
    }


def write_portfolio_simulation_review(
    backtest_result: dict[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_card = backtest_result.get("run_card")
    source_run_card_path = (
        str(run_card.get("run_card_json_path"))
        if isinstance(run_card, dict) and run_card.get("run_card_json_path")
        else None
    )
    states = [
        build_portfolio_simulation_state(result, source_run_card_path=source_run_card_path)
        for result in backtest_result.get("results", [])
        if isinstance(result, PortfolioResult)
    ]

    json_path = output_path / "portfolio_simulation_review.json"
    states_csv_path = output_path / "portfolio_simulation_states.csv"
    markdown_path = output_path / "portfolio_simulation_review.md"
    payload = {
        "state_count": len(states),
        "states": states,
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame([_state_summary_row(state) for state in states]).to_csv(states_csv_path, index=False)
    markdown_path.write_text(_render_review_markdown(states, states_csv_path), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "states_csv_path": str(states_csv_path),
        "markdown_path": str(markdown_path),
    }


def _latest_equity_row(equity_curve: pd.DataFrame) -> dict[str, Any]:
    if equity_curve.empty:
        return {}
    ordered = equity_curve.sort_values("date") if "date" in equity_curve.columns else equity_curve
    return dict(ordered.iloc[-1])


def _open_positions(trades: pd.DataFrame, *, equity: float) -> list[dict[str, Any]]:
    if trades.empty or "status" not in trades.columns:
        return []
    open_trades = trades[trades["status"].astype(str).eq("open")].copy()
    if open_trades.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in open_trades.sort_values(["buy_date", "asset_id"]).iterrows():
        buy_value = _float_value(row.get("buy_value"), default=0.0)
        rows.append(
            {
                "asset_id": str(row.get("asset_id", "")),
                "selection_date": str(row.get("selection_date", "")),
                "buy_date": str(row.get("buy_date", "")),
                "rank": _int_or_none(row.get("rank")),
                "score": _float_or_none(row.get("score")),
                "shares": _int_or_none(row.get("shares")) or 0,
                "buy_open": _float_or_none(row.get("buy_open")),
                "buy_value": buy_value,
                "position_weight": buy_value / equity if equity else 0.0,
                "status": "open",
            }
        )
    return rows


def _risk_level(drawdown: float) -> str:
    if drawdown <= BLOCK_DRAWDOWN:
        return "block"
    if drawdown <= WARNING_DRAWDOWN:
        return "warning"
    return "normal"


def _state_summary_row(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": state.get("trade_date"),
        "strategy_id": state.get("strategy_id"),
        "cash": state.get("cash"),
        "market_value": state.get("market_value"),
        "equity": state.get("equity"),
        "drawdown": state.get("drawdown"),
        "exposure_pct": state.get("exposure_pct"),
        "open_position_count": state.get("open_position_count"),
        "risk_level": state.get("risk_level"),
        "auto_trade_enabled": state.get("auto_trade_enabled"),
        "human_confirmation_required": state.get("human_confirmation_required"),
    }


def _render_state_markdown(state: dict[str, Any], positions_csv_path: Path) -> str:
    return "\n".join(
        [
            f"# Portfolio Simulation State {state.get('trade_date', '')}",
            "",
            "仅作为模拟组合状态，不执行自动下单。",
            "",
            f"- strategy_id: `{state.get('strategy_id', '')}`",
            f"- equity: `{state.get('equity', '')}`",
            f"- drawdown: `{state.get('drawdown', '')}`",
            f"- risk_level: `{state.get('risk_level', '')}`",
            f"- positions_csv: `{positions_csv_path}`",
            "",
        ]
    )


def _render_review_markdown(states: list[dict[str, Any]], states_csv_path: Path) -> str:
    lines = [
        "# Portfolio Simulation Review",
        "",
        "仅作为模拟组合复盘和建议层输入，不执行自动下单。",
        "",
        f"- state_count: `{len(states)}`",
        f"- states_csv: `{states_csv_path}`",
        "",
    ]
    for state in states:
        lines.append(
            f"- {state.get('strategy_id')}: equity={state.get('equity')}, "
            f"drawdown={state.get('drawdown')}, risk={state.get('risk_level')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _float_value(value: Any, *, default: float) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def _safe_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:80]
