from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.trade_advice.advice import validate_trade_advice


def load_simulation_states(paths: list[str | Path]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for path_value in paths:
        path = Path(path_value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_states = payload.get("states") if isinstance(payload, dict) else None
        if isinstance(raw_states, list):
            for state in raw_states:
                states.append(_state_with_source(state, path))
        elif isinstance(payload, dict):
            states.append(_state_with_source(payload, path))
        else:
            raise ValueError(f"simulation state artifact must be a JSON object: {path}")
    return sorted(states, key=lambda item: (str(item.get("trade_date", "")), str(item.get("strategy_id", ""))))


def build_virtual_portfolio_review(
    *,
    trade_date: str,
    portfolio_id: str,
    states: list[dict[str, Any]],
    advice: pd.DataFrame | None = None,
) -> dict[str, Any]:
    ordered_states = sorted(states, key=lambda item: (str(item.get("trade_date", "")), str(item.get("strategy_id", ""))))
    history_rows = [_history_row(state) for state in ordered_states]
    latest_state = ordered_states[-1] if ordered_states else {}
    latest_positions = [
        {**position, "strategy_id": latest_state.get("strategy_id"), "trade_date": latest_state.get("trade_date")}
        for position in latest_state.get("positions", [])
        if isinstance(position, dict)
    ]
    advice_frame = pd.DataFrame() if advice is None else advice.copy()
    return {
        "trade_date": trade_date,
        "portfolio_id": portfolio_id,
        "status": "manual_review_required",
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
        "state_count": len(ordered_states),
        "history_rows": history_rows,
        "latest_state": latest_state,
        "latest_positions": latest_positions,
        "risk_summary": _risk_summary(history_rows),
        "advice_summary": _advice_summary(advice_frame),
    }


def write_virtual_portfolio_review(
    review: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    trade_date = str(review["trade_date"])
    portfolio_id = _safe_stem(str(review["portfolio_id"]))
    stem = f"virtual_portfolio_review_{trade_date}_{portfolio_id}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    history_csv_path = output_path / f"{stem}_history.csv"
    positions_csv_path = output_path / f"{stem}_positions.csv"

    json_path.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(review.get("history_rows", [])).to_csv(history_csv_path, index=False)
    pd.DataFrame(review.get("latest_positions", [])).to_csv(positions_csv_path, index=False)
    markdown_path.write_text(_render_markdown(review, history_csv_path, positions_csv_path), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "history_csv_path": str(history_csv_path),
        "positions_csv_path": str(positions_csv_path),
    }


def _state_with_source(state: dict[str, Any], path: Path) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError(f"simulation state entry must be a JSON object: {path}")
    return {**state, "source_artifact_path": str(path)}


def _history_row(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": str(state.get("trade_date", "")),
        "strategy_id": str(state.get("strategy_id", "")),
        "cash": _float_value(state.get("cash")),
        "market_value": _float_value(state.get("market_value")),
        "equity": _float_value(state.get("equity")),
        "drawdown": _float_value(state.get("drawdown")),
        "exposure_pct": _float_value(state.get("exposure_pct")),
        "open_position_count": int(state.get("open_position_count") or 0),
        "risk_level": str(state.get("risk_level", "")),
        "source_artifact_path": str(state.get("source_artifact_path", "")),
    }


def _risk_summary(history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not history_rows:
        return {
            "latest_trade_date": None,
            "latest_risk_level": "missing",
            "latest_drawdown": None,
            "max_drawdown": None,
            "max_exposure_pct": None,
            "warning_state_count": 0,
            "block_state_count": 0,
            "manual_review_required": True,
        }
    latest = history_rows[-1]
    drawdowns = [float(row["drawdown"]) for row in history_rows if row.get("drawdown") is not None]
    exposures = [float(row["exposure_pct"]) for row in history_rows if row.get("exposure_pct") is not None]
    return {
        "latest_trade_date": latest.get("trade_date"),
        "latest_risk_level": latest.get("risk_level"),
        "latest_drawdown": latest.get("drawdown"),
        "max_drawdown": min(drawdowns) if drawdowns else None,
        "max_exposure_pct": max(exposures) if exposures else None,
        "warning_state_count": sum(1 for row in history_rows if row.get("risk_level") == "warning"),
        "block_state_count": sum(1 for row in history_rows if row.get("risk_level") == "block"),
        "manual_review_required": True,
    }


def _advice_summary(advice: pd.DataFrame) -> dict[str, Any]:
    if advice.empty:
        return {
            "status": "manual_review_required",
            "advice_count": 0,
            "issue_count": 0,
            "target_exposure_pct": 0.0,
            "action_counts": {},
            "auto_trade_enabled": False,
            "human_confirmation_required": True,
        }
    issues = validate_trade_advice(advice)
    target_weights = pd.to_numeric(advice.get("target_weight", 0.0), errors="coerce").fillna(0.0)
    return {
        "status": "manual_review_required",
        "advice_count": int(len(advice)),
        "issue_count": int(len(issues)),
        "target_exposure_pct": float(target_weights.sum()),
        "action_counts": {
            str(key): int(value)
            for key, value in advice["action"].astype(str).value_counts().sort_index().items()
        }
        if "action" in advice.columns
        else {},
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }


def _render_markdown(review: dict[str, Any], history_csv_path: Path, positions_csv_path: Path) -> str:
    risk = review["risk_summary"]
    advice = review["advice_summary"]
    return "\n".join(
        [
            f"# Virtual Portfolio Review {review['trade_date']}",
            "",
            "仅作为虚拟组合跟踪与人工复核入口，不执行自动下单。",
            "",
            f"- portfolio_id: `{review['portfolio_id']}`",
            f"- status: `{review['status']}`",
            f"- state_count: `{review['state_count']}`",
            f"- latest_risk_level: `{risk['latest_risk_level']}`",
            f"- max_drawdown: `{risk['max_drawdown']}`",
            f"- advice_status: `{advice['status']}`",
            f"- advice_count: `{advice['advice_count']}`",
            f"- history_csv: `{history_csv_path}`",
            f"- positions_csv: `{positions_csv_path}`",
            "",
        ]
    )


def _float_value(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _safe_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:80]
