from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GROUP_TITLES = {
    "delivery": "Delivery",
    "agent": "Agent",
    "simulation": "Simulation",
    "factor_validation": "Factor Validation",
    "technical_performance": "Technical Performance",
    "watchlist": "Watchlist",
}


def load_aggregate_artifact_payloads(rollup: dict[str, Any]) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for artifact in rollup.get("artifacts", []):
        path = Path(str(artifact.get("path", "")))
        if not path.exists() or path.suffix.lower() != ".json":
            continue
        try:
            payloads[str(path)] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payloads[str(path)] = {"_load_error": "invalid_json"}
    return payloads


def build_p2_aggregate_review(
    *,
    trade_date: str,
    rollup: dict[str, Any],
    artifact_payloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payloads = artifact_payloads or {}
    artifacts = list(rollup.get("artifacts", []))
    sections = [
        _build_section(artifact, payloads.get(str(artifact.get("path", ""))))
        for artifact in artifacts
    ]
    blockers = _collect_blockers(sections)
    warning_count = sum(
        1
        for section in sections
        if section["status"] in {"warning", "manual_review_required"}
    )
    status = "blocked" if blockers else "review_required" if warning_count else "ready"
    return {
        "trade_date": trade_date,
        "run_id": rollup.get("run_id"),
        "status": status,
        "blocker_count": len(blockers),
        "warning_count": warning_count,
        "blockers": blockers,
        "sections": sections,
        "source_rollup_status": rollup.get("status"),
        "auto_trade_enabled": False,
        "human_confirmation_required": True,
    }


def write_p2_aggregate_review(
    review: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    trade_date = str(review["trade_date"])
    json_path = output_path / f"p2_aggregate_review_{trade_date}.json"
    markdown_path = output_path / f"p2_aggregate_review_{trade_date}.md"
    json_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(review), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def _build_section(artifact: dict[str, Any], payload: Any) -> dict[str, Any]:
    group = str(artifact.get("group", "unknown"))
    exists = bool(artifact.get("exists"))
    required = bool(artifact.get("required"))
    if not exists:
        status = "missing_required" if required else "missing_optional"
        summary = {"message": "artifact missing"}
    else:
        status, summary = _payload_status_and_summary(group, payload)
    return {
        "group": group,
        "title": GROUP_TITLES.get(group, group.replace("_", " ").title()),
        "name": str(artifact.get("name", "")),
        "path": str(artifact.get("path", "")),
        "required": required,
        "exists": exists,
        "status": status,
        "summary": summary,
    }


def _payload_status_and_summary(group: str, payload: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return "present", {}
    if payload.get("_load_error"):
        return "warning", {"load_error": payload["_load_error"]}
    if group == "delivery":
        return "present", {
            "item_count": int(payload.get("item_count") or len(payload.get("items", [])))
        }
    if group == "agent":
        review = payload.get("review", {}) if isinstance(payload.get("review"), dict) else {}
        blocker_count = int(review.get("blocker_count") or 0)
        observations = payload.get("observations", [])
        observation_count = len(observations) if isinstance(observations, list) else 0
        return (
            "blocked" if blocker_count else str(review.get("status") or "present"),
            {
                "review_status": review.get("status"),
                "blocker_count": blocker_count,
                "observation_count": observation_count,
            },
        )
    if group == "simulation":
        risk = payload.get("risk_summary", {}) if isinstance(payload.get("risk_summary"), dict) else {}
        advice = (
            payload.get("advice_summary", {})
            if isinstance(payload.get("advice_summary"), dict)
            else {}
        )
        latest_risk = str(risk.get("latest_risk_level") or "")
        issue_count = int(advice.get("issue_count") or 0)
        status = (
            "blocked"
            if latest_risk == "block" or issue_count
            else str(payload.get("status") or "manual_review_required")
        )
        return (
            status,
            {
                "latest_risk_level": latest_risk,
                "max_drawdown": risk.get("max_drawdown"),
                "advice_status": advice.get("status"),
                "advice_count": int(advice.get("advice_count") or 0),
                "advice_issue_count": issue_count,
            },
        )
    if group == "factor_validation":
        approval = payload.get("approval", {}) if isinstance(payload.get("approval"), dict) else {}
        approval_status = str(approval.get("status") or "present")
        return (
            "blocked" if approval_status == "rejected" else approval_status,
            {"approval_status": approval_status, "reason": approval.get("reason")},
        )
    if group == "technical_performance":
        gate = payload.get("gate", {}) if isinstance(payload.get("gate"), dict) else {}
        gate_status = str(gate.get("status") or "present")
        return (
            "blocked" if gate_status == "rejected" else gate_status,
            {"gate_status": gate_status, "reason": gate.get("reason")},
        )
    return "present", {}


def _collect_blockers(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for section in sections:
        if section["status"] == "missing_required":
            blockers.append(
                {
                    "code": "missing_required_artifact",
                    "group": section["group"],
                    "name": section["name"],
                    "path": section["path"],
                    "message": "required P2 artifact is missing",
                }
            )
        elif section["status"] == "blocked":
            blockers.append(
                {
                    "code": f"{section['group']}_blocked",
                    "group": section["group"],
                    "name": section["name"],
                    "path": section["path"],
                    "message": f"{section['title']} section is blocked",
                }
            )
    return blockers


def _render_markdown(review: dict[str, Any]) -> str:
    lines = [
        f"# P2 Aggregate Review {review['trade_date']}",
        "",
        f"- Status: `{review['status']}`",
        f"- Blockers: `{review['blocker_count']}`",
        f"- Warnings: `{review['warning_count']}`",
        "",
        "## Review Blockers",
        "",
    ]
    if review["blockers"]:
        for blocker in review["blockers"]:
            lines.append(
                f"- `{blocker['code']}` {blocker['group']}/{blocker['name']}: {blocker['message']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Sections", ""])
    for section in review["sections"]:
        lines.extend(
            [
                f"### {section['title']}",
                "",
                f"- Status: `{section['status']}`",
                f"- Path: `{section['path']}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
