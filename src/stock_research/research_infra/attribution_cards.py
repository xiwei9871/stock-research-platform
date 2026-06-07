from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import pandas as pd


VALID_CAUSE_CATEGORIES = {
    "bad_buy",
    "missed_winner",
    "sell_too_early",
    "drawdown_control",
    "replacement_failure",
    "research_coverage_gap",
    "industry_regime_mismatch",
    "market_regime_mismatch",
    "data_quality_gap",
}

VALID_PREVENTABILITY = {
    "preventable",
    "partly_preventable",
    "not_preventable",
    "unknown",
}

VALID_OUTCOME_TYPES = {
    "failure",
    "success",
    "mixed",
}


class AttributionCardValidationError(ValueError):
    """Raised when an attribution card is missing required review context."""


@dataclass(frozen=True)
class AttributionCard:
    case_id: str
    asset_id: str
    ts_code: str
    trade_date: str
    strategy_context: str
    failure_or_success_type: str
    primary_cause: str
    secondary_causes: list[str]
    evidence: dict[str, Any]
    counterfactual: str
    preventability: str
    recommended_rule_change: str
    confidence: str

    def __post_init__(self) -> None:
        missing = [
            field_name
            for field_name in [
                "case_id",
                "asset_id",
                "ts_code",
                "trade_date",
                "strategy_context",
                "failure_or_success_type",
                "primary_cause",
                "counterfactual",
                "preventability",
                "recommended_rule_change",
                "confidence",
            ]
            if not str(getattr(self, field_name)).strip()
        ]
        invalid: list[str] = []
        if self.failure_or_success_type not in VALID_OUTCOME_TYPES:
            invalid.append("failure_or_success_type")
        if self.primary_cause not in VALID_CAUSE_CATEGORIES:
            invalid.append(f"primary_cause:{self.primary_cause}")
        invalid_secondary = [
            cause for cause in self.secondary_causes if cause not in VALID_CAUSE_CATEGORIES
        ]
        if invalid_secondary:
            invalid.append("secondary_causes:" + ",".join(invalid_secondary))
        if self.preventability not in VALID_PREVENTABILITY:
            invalid.append("preventability")
        if not self.evidence:
            missing.append("evidence")
        if missing or invalid:
            parts = []
            if missing:
                parts.append("missing " + ", ".join(sorted(set(missing))))
            if invalid:
                parts.append("invalid " + ", ".join(sorted(set(invalid))))
            raise AttributionCardValidationError("; ".join(parts))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def build_attribution_cards_from_frame(frame: pd.DataFrame) -> list[AttributionCard]:
    cards: list[AttributionCard] = []
    for _, row in frame.iterrows():
        cards.append(
            AttributionCard(
                case_id=str(row.get("case_id", "")),
                asset_id=str(row.get("asset_id", "")),
                ts_code=str(row.get("ts_code", "")),
                trade_date=str(row.get("trade_date", "")),
                strategy_context=str(row.get("strategy_context", "")),
                failure_or_success_type=str(row.get("failure_or_success_type", "")),
                primary_cause=str(row.get("primary_cause", "")),
                secondary_causes=_string_list(row.get("secondary_causes")),
                evidence=_dict_value(row.get("evidence")),
                counterfactual=str(row.get("counterfactual", "")),
                preventability=str(row.get("preventability", "")),
                recommended_rule_change=str(row.get("recommended_rule_change", "")),
                confidence=str(row.get("confidence", "")),
            )
        )
    return cards


def export_attribution_cards(
    cards: list[AttributionCard] | tuple[AttributionCard, ...],
) -> list[dict[str, Any]]:
    return [card.to_dict() for card in cards]


def render_attribution_card_markdown(card: AttributionCard | dict[str, Any]) -> str:
    payload = card.to_dict() if isinstance(card, AttributionCard) else _jsonable(card)
    lines = [
        f"# Attribution Card: {payload.get('case_id', '')}",
        "",
        "## Context",
        "",
        "```json",
        json.dumps(
            {
                "asset_id": payload.get("asset_id", ""),
                "ts_code": payload.get("ts_code", ""),
                "trade_date": payload.get("trade_date", ""),
                "strategy_context": payload.get("strategy_context", ""),
                "failure_or_success_type": payload.get("failure_or_success_type", ""),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Cause",
        "",
        f"- primary_cause: {payload.get('primary_cause', '')}",
        f"- secondary_causes: {', '.join(payload.get('secondary_causes') or [])}",
        f"- preventability: {payload.get('preventability', '')}",
        f"- confidence: {payload.get('confidence', '')}",
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(
            payload.get("evidence", {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Counterfactual",
        "",
        str(payload.get("counterfactual", "")),
        "",
        "## Recommended Rule Change",
        "",
        str(payload.get("recommended_rule_change", "")),
        "",
    ]
    return "\n".join(lines)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if pd.isna(value):
        return []
    return [str(value)]


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if not isinstance(value, (list, tuple, set)) and pd.isna(value):
        return {}
    raise AttributionCardValidationError("evidence must be a dict")


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
