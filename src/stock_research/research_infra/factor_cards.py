from __future__ import annotations

import json
from typing import Any

import pandas as pd


class FactorCardValidationError(ValueError):
    """Raised when a factor evaluation card is missing required context."""


def build_factor_evaluation_card(
    eval_report: dict[str, Any],
    *,
    sample_window: dict[str, Any],
    universe: dict[str, Any],
    label_definition: dict[str, Any],
    regime_breakdown: dict[str, Any] | None = None,
    industry_exposure: dict[str, Any] | None = None,
    drawdown_notes: list[str] | None = None,
    warnings: list[str] | None = None,
    topn_hit_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_required_context(
        sample_window=sample_window,
        universe=universe,
        label_definition=label_definition,
    )
    return {
        "factor_name": str(eval_report.get("factor_name", "")),
        "sample_window": _jsonable(sample_window),
        "universe": _jsonable(universe),
        "label_definition": _jsonable(label_definition),
        "ic_summary": _jsonable(eval_report.get("ic_summary", {})),
        "rank_ic_summary": _jsonable(eval_report.get("rank_ic_summary", {})),
        "quantile_return_summary": _summarize_quantile_returns(eval_report),
        "topn_hit_summary": _jsonable(topn_hit_summary or {"status": "not_provided"}),
        "turnover_summary": _summarize_turnover(eval_report.get("turnover")),
        "regime_breakdown": _jsonable(regime_breakdown or {}),
        "industry_exposure": _jsonable(industry_exposure or {}),
        "drawdown_notes": _jsonable(drawdown_notes or []),
        "warnings": _jsonable(warnings or []),
    }


def render_factor_evaluation_card_markdown(card: dict[str, Any]) -> str:
    lines = [
        f"# Factor Evaluation Card: {card.get('factor_name', '')}",
        "",
        "## Sample",
        "",
        "```json",
        json.dumps(
            {
                "sample_window": card.get("sample_window", {}),
                "universe": card.get("universe", {}),
                "label_definition": card.get("label_definition", {}),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## IC Summary",
        "",
        "```json",
        json.dumps(
            card.get("ic_summary", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Rank IC Summary",
        "",
        "```json",
        json.dumps(
            card.get("rank_ic_summary", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Quantile Returns",
        "",
        "```json",
        json.dumps(
            card.get("quantile_return_summary", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Turnover",
        "",
        "```json",
        json.dumps(
            card.get("turnover_summary", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
    ]
    warnings = card.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", "", *[f"- {warning}" for warning in warnings]])
    return "\n".join(lines) + "\n"


def _validate_required_context(
    *,
    sample_window: dict[str, Any],
    universe: dict[str, Any],
    label_definition: dict[str, Any],
) -> None:
    missing = []
    if not sample_window:
        missing.append("sample_window")
    if not universe:
        missing.append("universe")
    if not label_definition:
        missing.append("label_definition")
    if missing:
        raise FactorCardValidationError(
            "missing required factor card context: " + ", ".join(missing)
        )


def _summarize_quantile_returns(eval_report: dict[str, Any]) -> dict[str, Any]:
    quantile = eval_report.get("quantile_return")
    spread = eval_report.get("top_bottom_spread")
    summary: dict[str, Any] = {
        "row_count": _frame_row_count(quantile),
        "mean_top_bottom_spread": None,
    }
    if isinstance(spread, pd.DataFrame) and not spread.empty:
        values = pd.to_numeric(
            spread.get("top_bottom_spread"),
            errors="coerce",
        ).dropna()
        if not values.empty:
            summary["mean_top_bottom_spread"] = float(values.mean())
    return summary


def _summarize_turnover(turnover: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "row_count": _frame_row_count(turnover),
        "mean_turnover": None,
    }
    if isinstance(turnover, pd.DataFrame) and not turnover.empty:
        values = pd.to_numeric(turnover.get("turnover"), errors="coerce").dropna()
        if not values.empty:
            summary["mean_turnover"] = float(values.mean())
    return summary


def _frame_row_count(value: Any) -> int:
    if isinstance(value, pd.DataFrame):
        return int(len(value))
    return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    return value
