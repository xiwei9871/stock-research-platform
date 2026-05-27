from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import pandas as pd


ADVICE_COLUMNS = [
    "trade_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "industry",
    "decision_label",
    "score",
    "action",
    "target_weight",
    "target_value",
    "advice_status",
    "execution_status",
    "requires_human_confirmation",
    "auto_trade_enabled",
    "evidence_artifact_id",
    "reason",
]


@dataclass(frozen=True)
class TradeAdvicePolicy:
    max_single_position_pct: float = 0.10
    max_industry_position_pct: float = 0.30
    target_total_exposure_pct: float = 0.60
    drawdown_defensive_threshold: float = -0.10
    defensive_exposure_multiplier: float = 0.50


def generate_trade_advice(
    *,
    trade_date: str,
    simulation_state: dict[str, Any],
    candidates: pd.DataFrame,
    policy: TradeAdvicePolicy = TradeAdvicePolicy(),
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=ADVICE_COLUMNS)

    equity = _float_value(simulation_state.get("equity"), default=0.0)
    drawdown = _float_value(simulation_state.get("drawdown"), default=0.0)
    risk_level = str(simulation_state.get("risk_level", "normal"))
    target_total = float(policy.target_total_exposure_pct)
    if drawdown <= policy.drawdown_defensive_threshold or risk_level in {"warning", "block"}:
        target_total *= float(policy.defensive_exposure_multiplier)
    if risk_level == "block":
        target_total = 0.0

    active = candidates.copy()
    active["score"] = pd.to_numeric(active.get("score", 0.0), errors="coerce").fillna(0.0)
    active = active.sort_values("score", ascending=False).reset_index(drop=True)
    eligible_mask = active["decision_label"].astype(str).isin(["候选", "观察"])
    eligible_count = int(eligible_mask.sum())
    base_weight = target_total / eligible_count if eligible_count else 0.0
    industry_allocated: dict[str, float] = {}
    rows: list[dict[str, Any]] = []

    for _, row in active.iterrows():
        label = str(row.get("decision_label", ""))
        industry = str(row.get("industry", ""))
        evidence_id = str(row.get("evidence_artifact_id", ""))
        if target_total <= 0 or label in {"剔除", "谨慎"}:
            action = "no_buy"
            target_weight = 0.0
            reason = "risk gate blocks new exposure" if target_total <= 0 else f"decision_label={label}"
        else:
            industry_room = max(
                0.0,
                float(policy.max_industry_position_pct) - industry_allocated.get(industry, 0.0),
            )
            target_weight = min(float(policy.max_single_position_pct), base_weight, industry_room)
            action = "consider_buy" if target_weight > 0 else "no_buy"
            reason = "position advice only; human confirmation required"
        industry_allocated[industry] = industry_allocated.get(industry, 0.0) + target_weight
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": str(row.get("asset_id", "")),
                "stock_code": str(row.get("stock_code", "")),
                "stock_name": str(row.get("stock_name", "")),
                "industry": industry,
                "decision_label": label,
                "score": float(row.get("score", 0.0)),
                "action": action,
                "target_weight": target_weight,
                "target_value": target_weight * equity,
                "advice_status": "pending_human_review",
                "execution_status": "not_executed",
                "requires_human_confirmation": True,
                "auto_trade_enabled": False,
                "evidence_artifact_id": evidence_id,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows, columns=ADVICE_COLUMNS)


def validate_trade_advice(advice: pd.DataFrame) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if advice.empty:
        return issues
    for index, row in advice.reset_index(drop=True).iterrows():
        if str(row.get("execution_status", "")) != "not_executed":
            issues.append(
                {
                    "code": "execution_not_allowed",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "trade advice must not submit or execute orders",
                }
            )
        if bool(row.get("auto_trade_enabled", False)):
            issues.append(
                {
                    "code": "auto_trade_not_allowed",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "auto_trade_enabled must remain false",
                }
            )
        if not str(row.get("evidence_artifact_id", "")).strip():
            issues.append(
                {
                    "code": "missing_evidence",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "trade advice must cite an evidence artifact",
                }
            )
    return issues


def write_trade_advice(
    *,
    trade_date: str,
    advice: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / f"trade_advice_{trade_date}.csv"
    json_path = output_path / f"trade_advice_{trade_date}.json"
    markdown_path = output_path / f"trade_advice_{trade_date}.md"
    issues = validate_trade_advice(advice)

    advice.to_csv(csv_path, index=False)
    payload = {
        "trade_date": trade_date,
        "advice_count": int(len(advice)),
        "issue_count": int(len(issues)),
        "issues": issues,
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
        "items": advice.to_dict("records"),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(trade_date, advice, issues), encoding="utf-8")
    return {
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _render_markdown(trade_date: str, advice: pd.DataFrame, issues: list[dict[str, Any]]) -> str:
    lines = [
        f"# Trade Advice {trade_date}",
        "",
        "待人工确认；不执行自动下单。",
        "",
        f"- advice_count: `{len(advice)}`",
        f"- issue_count: `{len(issues)}`",
        "",
    ]
    if advice.empty:
        lines.append("No advice rows.")
    else:
        lines.append("| Asset | Action | Target Weight | Evidence |")
        lines.append("| --- | --- | ---: | --- |")
        for _, row in advice.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("asset_id", "")),
                        str(row.get("action", "")),
                        f"{_float_value(row.get('target_weight'), default=0.0):.4f}",
                        str(row.get("evidence_artifact_id", "")),
                    ]
                )
                + " |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _float_value(value: Any, *, default: float) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default
