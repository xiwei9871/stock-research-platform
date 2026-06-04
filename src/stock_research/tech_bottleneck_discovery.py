from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


CHOKEPOINT_DIMENSIONS = [
    "terminal_demand_certainty",
    "single_point_importance",
    "supply_concentration",
    "capacity_expansion_difficulty",
    "technical_barrier",
    "qualification_or_customer_switching_cost",
    "substitution_difficulty",
    "value_capture_power",
]

UNDERPRICING_DIMENSIONS = [
    "market_cap_room",
    "low_sell_side_coverage",
    "low_institutional_attention",
    "old_business_mispricing",
    "new_business_not_in_numbers",
    "valuation_vs_peers",
    "price_not_overheated",
    "narrative_early_stage",
]

PACKET_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "trade_date",
    "terminal_demand",
    "supply_chain_node",
    "company_exposure",
    "chokepoint_score",
    "underpricing_score",
    "evidence_score",
    "trend_score",
    "catalyst_score",
    "risk_penalty",
    "tech_bottleneck_score",
    "candidate_state",
    "one_sentence_thesis",
    "market_misconception",
    "evidence_items",
    "review_decision",
    "review_reason",
]


def build_tech_bottleneck_packets(
    *,
    candidates: pd.DataFrame,
    evidence: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=PACKET_COLUMNS)

    evidence_lookup = _evidence_lookup(evidence)
    rows: list[dict[str, Any]] = []
    for candidate in candidates.to_dict("records"):
        asset_id = _safe_text(candidate.get("asset_id"))
        evidence_items = evidence_lookup.get(asset_id, [])
        chokepoint_score = _sum_dimensions(candidate, CHOKEPOINT_DIMENSIONS)
        underpricing_score = _sum_dimensions(candidate, UNDERPRICING_DIMENSIONS)
        evidence_score = _evidence_score(evidence_items)
        trend_score = _score_from_total(chokepoint_score, 40.0)
        catalyst_score = _default_catalyst_score(evidence_items)
        risk_penalty = _bounded_float(candidate.get("risk_penalty"), default=0.0, lower=0.0, upper=5.0)
        tech_bottleneck_score = round(
            0.25 * trend_score
            + 0.25 * _score_from_total(chokepoint_score, 40.0)
            + 0.20 * evidence_score
            + 0.15 * _score_from_total(underpricing_score, 40.0)
            + 0.10 * catalyst_score
            - 0.15 * risk_penalty,
            4,
        )
        state = _candidate_state(
            chokepoint_score=chokepoint_score,
            evidence_items=evidence_items,
            tech_bottleneck_score=tech_bottleneck_score,
            risk_penalty=risk_penalty,
        )
        stock_name = _safe_text(candidate.get("stock_name"))
        terminal_demand = _safe_text(candidate.get("terminal_demand"))
        supply_chain_node = _safe_text(candidate.get("supply_chain_node"))
        exposure = _safe_text(candidate.get("company_exposure"))
        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "stock_name": stock_name,
                "trade_date": _safe_text(candidate.get("trade_date")),
                "terminal_demand": terminal_demand,
                "supply_chain_node": supply_chain_node,
                "company_exposure": exposure,
                "chokepoint_score": chokepoint_score,
                "underpricing_score": underpricing_score,
                "evidence_score": evidence_score,
                "trend_score": trend_score,
                "catalyst_score": catalyst_score,
                "risk_penalty": risk_penalty,
                "tech_bottleneck_score": tech_bottleneck_score,
                "candidate_state": state,
                "one_sentence_thesis": (
                    f"{stock_name} 可能处在 {terminal_demand} 的 {supply_chain_node} 咽喉点；"
                    f"{exposure}"
                ),
                "market_misconception": (
                    f"市场可能仍按旧业务或普通供应商定价，但证据显示公司可能暴露于 {supply_chain_node}。"
                ),
                "evidence_items": evidence_items,
                "review_decision": "pending_review",
                "review_reason": "",
            }
        )
    return pd.DataFrame(rows, columns=PACKET_COLUMNS).sort_values(
        ["candidate_state", "tech_bottleneck_score", "asset_id"],
        ascending=[True, False, True],
        kind="mergesort",
    )


def render_tech_bottleneck_markdown(packet: dict[str, Any]) -> str:
    evidence_lines = []
    for item in packet.get("evidence_items", []):
        evidence_lines.append(
            f"- [{item.get('evidence_tier')}] {item.get('claim')} "
            f"({item.get('source_type')}, {item.get('source_date')})"
        )
    if not evidence_lines:
        evidence_lines = ["- No evidence items supplied."]
    return "\n".join(
        [
            f"# {packet.get('stock_name')} tech-bottleneck-discovery Packet",
            "",
            f"- Asset: `{packet.get('asset_id')}`",
            f"- Trade date: `{packet.get('trade_date')}`",
            f"- State: `{packet.get('candidate_state')}`",
            f"- Score: `{packet.get('tech_bottleneck_score')}`",
            "",
            "## Thesis",
            "",
            str(packet.get("one_sentence_thesis", "")),
            "",
            "## Market Misconception",
            "",
            str(packet.get("market_misconception", "")),
            "",
            "## Evidence",
            "",
            *evidence_lines,
            "",
            "## Review",
            "",
            f"- Decision: `{packet.get('review_decision', 'pending_review')}`",
            f"- Reason: {packet.get('review_reason', '')}",
            "",
        ]
    )


def write_tech_bottleneck_artifacts(
    *,
    packets: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "packets.json"
    csv_path = output_dir / "packets.csv"
    summary_path = output_dir / "summary.md"
    records = packets.to_dict("records")
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    packets_for_csv = packets.copy()
    if "evidence_items" in packets_for_csv.columns:
        packets_for_csv["evidence_items"] = packets_for_csv["evidence_items"].map(
            lambda value: json.dumps(value, ensure_ascii=False)
        )
    packets_for_csv.to_csv(csv_path, index=False)
    summary_lines = ["# tech-bottleneck-discovery Summary", ""]
    for packet in records:
        asset_id = str(packet.get("asset_id", "")).replace(":", "_")
        markdown_path = output_dir / f"{asset_id}.md"
        markdown_path.write_text(render_tech_bottleneck_markdown(packet), encoding="utf-8")
        summary_lines.append(
            f"- `{packet.get('asset_id')}` {packet.get('stock_name')} "
            f"{packet.get('candidate_state')} score={packet.get('tech_bottleneck_score')}"
        )
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "summary": summary_path}


def _evidence_lookup(evidence: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if evidence.empty:
        return {}
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in evidence.to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if not asset_id:
            continue
        lookup.setdefault(asset_id, []).append(
            {
                "evidence_tier": _normalize_tier(row.get("evidence_tier")),
                "source_type": _safe_text(row.get("source_type")),
                "source_url_or_path": _safe_text(row.get("source_url_or_path")),
                "source_date": _safe_text(row.get("source_date")),
                "claim": _safe_text(row.get("claim")),
                "supports": _safe_text(row.get("supports")),
                "contradicts": _safe_text(row.get("contradicts")),
                "confidence": _safe_text(row.get("confidence")) or "medium",
                "freshness": _safe_text(row.get("freshness")) or "unknown",
            }
        )
    return lookup


def _candidate_state(
    *,
    chokepoint_score: float,
    evidence_items: list[dict[str, Any]],
    tech_bottleneck_score: float,
    risk_penalty: float,
) -> str:
    tier1_count = sum(1 for item in evidence_items if item.get("evidence_tier") == "tier1")
    tier2_or_better = sum(
        1 for item in evidence_items if item.get("evidence_tier") in {"tier1", "tier2"}
    )
    if risk_penalty >= 4.5 or chokepoint_score < 16 or tier2_or_better == 0:
        return "reject"
    if tier1_count >= 2 and chokepoint_score >= 33 and tech_bottleneck_score >= 3.0:
        return "conviction_candidate"
    if tier1_count >= 2 and chokepoint_score >= 26:
        return "probe"
    if tier1_count >= 1 or tier2_or_better >= 2:
        return "research"
    return "watch"


def _evidence_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    score = 0.0
    for item in items:
        tier = item.get("evidence_tier")
        if tier == "tier1":
            score += 2.5
        elif tier == "tier2":
            score += 1.5
        else:
            score += 1.0
    return min(round(score, 2), 5.0)


def _default_catalyst_score(items: list[dict[str, Any]]) -> float:
    if any(item.get("source_type") in {"announcement", "earnings_call"} for item in items):
        return 4.0
    if any(item.get("evidence_tier") == "tier1" for item in items):
        return 3.0
    return 1.0 if items else 0.0


def _sum_dimensions(row: dict[str, Any], dimensions: list[str]) -> float:
    return round(
        sum(_bounded_float(row.get(column), default=0.0, lower=0.0, upper=5.0) for column in dimensions),
        2,
    )


def _score_from_total(total: float, max_total: float) -> float:
    if max_total <= 0:
        return 0.0
    return round(max(0.0, min(5.0, total / max_total * 5.0)), 4)


def _bounded_float(value: Any, *, default: float, lower: float, upper: float) -> float:
    try:
        if pd.isna(value):
            return default
        number = float(value)
    except Exception:
        return default
    return max(lower, min(upper, number))


def _normalize_tier(value: Any) -> str:
    normalized = _safe_text(value).lower().replace(" ", "")
    if normalized in {"1", "tier1", "t1"}:
        return "tier1"
    if normalized in {"2", "tier2", "t2"}:
        return "tier2"
    return "tier3"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
