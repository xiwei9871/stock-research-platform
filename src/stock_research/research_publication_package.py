from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.research_publish_gate import get_research_publish_gate
from stock_research.research_objects import stable_id


DEFAULT_PREVIEW_ROOT = Path("outputs/research/research_publication_preview_v1")
ENTRYPOINT_LOCK_REPORT = "publication_entrypoint_lock_report.md"


def build_research_publication_package(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    gate = get_research_publish_gate(trade_date=trade_date, service=service)
    summary = _package_summary(gate.get("summary"))
    publishable = bool(gate.get("research_ready_for_publication"))
    package = {
        "trade_date": str(trade_date),
        "package_id": stable_id("research_publication_package", trade_date, gate.get("status"), summary),
        "publishable": publishable,
        "actual_publish_enabled": False,
        "internal_snapshot_enabled": publishable,
        "external_delivery_enabled": False,
        "gate": {
            "status": str(gate.get("status") or "empty"),
            "research_ready_for_publication": publishable,
            "actual_publish_enabled": False,
            "internal_snapshot_enabled": publishable,
            "external_delivery_enabled": False,
        },
        "summary": summary,
        "sections": [
            {
                "section_type": "research_queue_summary",
                "title": "研究队列摘要",
                "items": [
                    {
                        "case_count": summary["case_count"],
                        "claim_count": summary["claim_count"],
                        "evidence_count": summary["evidence_count"],
                        "evidence_link_count": summary["evidence_link_count"],
                        "gap_count": summary["gap_count"],
                        "pending_gap_count": summary["pending_gap_count"],
                        "reviewed_gap_count": summary["reviewed_gap_count"],
                    }
                ],
            },
            {
                "section_type": "blocked_cases",
                "title": "发布阻塞项",
                "items": [_blocked_case_item(item) for item in (gate.get("top_blocked_cases") or [])[:5]],
            },
        ],
        "warnings": [_notice(item) for item in gate.get("warnings") or []],
        "blockers": [_notice(item) for item in gate.get("blockers") or []],
    }
    return research_publication_package_read_model(package)


def research_publication_package_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "package_id": str(payload.get("package_id") or ""),
        "publishable": bool(payload.get("publishable")),
        "actual_publish_enabled": False,
        "internal_snapshot_enabled": bool(payload.get("internal_snapshot_enabled")),
        "external_delivery_enabled": False,
        "gate": _gate(payload.get("gate")),
        "summary": _summary_read_model(payload.get("summary")),
        "sections": [_section(item) for item in sections],
        "warnings": [_notice(item) for item in payload.get("warnings") or []],
        "blockers": [_notice(item) for item in payload.get("blockers") or []],
    }


def run_research_publication_preview(
    *,
    trade_date: str,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    package = build_research_publication_package(trade_date, service=service)
    resolved_output_dir = Path(output_dir) if output_dir is not None else DEFAULT_PREVIEW_ROOT / trade_date
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    json_path = resolved_output_dir / "research_publication_package.json"
    markdown_path = resolved_output_dir / "research_publication_preview.md"
    json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_preview_markdown(package), encoding="utf-8")
    return {
        "status": "preview_generated",
        "dry_run": True,
        "trade_date": package["trade_date"],
        "package_id": package["package_id"],
        "publishable": package["publishable"],
        "actual_publish_enabled": False,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "blocker_count": len(package["blockers"]),
        "warning_count": len(package["warnings"]),
    }


def write_publication_entrypoint_lock_report(output_dir: str | Path) -> str:
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    path = resolved_output_dir / ENTRYPOINT_LOCK_REPORT
    path.write_text(_entrypoint_lock_report(), encoding="utf-8")
    return str(path)


def _package_summary(value: Any) -> dict[str, int]:
    summary = value if isinstance(value, dict) else {}
    return {
        "case_count": _int(summary.get("case_count")),
        "claim_count": _int(summary.get("claim_count")),
        "evidence_count": _int(summary.get("evidence_artifact_count")),
        "evidence_link_count": _int(summary.get("evidence_link_count")),
        "gap_count": _int(summary.get("evidence_gap_count")),
        "reviewed_gap_count": _int(summary.get("reviewed_gap_count")),
        "pending_gap_count": _int(summary.get("pending_gap_count")),
        "request_more_evidence_count": _int(summary.get("request_more_evidence_count")),
        "deferred_gap_count": _int(summary.get("deferred_gap_count")),
        "unmatched_digest_count": _int(summary.get("unmatched_digest_count")),
        "error_count": _int(summary.get("error_count")),
    }


def _summary_read_model(value: Any) -> dict[str, int]:
    summary = value if isinstance(value, dict) else {}
    return {
        "case_count": _int(summary.get("case_count")),
        "claim_count": _int(summary.get("claim_count")),
        "evidence_count": _int(summary.get("evidence_count")),
        "evidence_link_count": _int(summary.get("evidence_link_count")),
        "gap_count": _int(summary.get("gap_count")),
        "reviewed_gap_count": _int(summary.get("reviewed_gap_count")),
        "pending_gap_count": _int(summary.get("pending_gap_count")),
        "request_more_evidence_count": _int(summary.get("request_more_evidence_count")),
        "deferred_gap_count": _int(summary.get("deferred_gap_count")),
        "unmatched_digest_count": _int(summary.get("unmatched_digest_count")),
        "error_count": _int(summary.get("error_count")),
    }


def _gate(value: Any) -> dict[str, Any]:
    gate = value if isinstance(value, dict) else {}
    return {
        "status": str(gate.get("status") or "empty"),
        "research_ready_for_publication": bool(gate.get("research_ready_for_publication")),
        "actual_publish_enabled": False,
        "internal_snapshot_enabled": bool(gate.get("internal_snapshot_enabled")),
        "external_delivery_enabled": False,
    }


def _section(value: Any) -> dict[str, Any]:
    section = value if isinstance(value, dict) else {}
    items = section.get("items") if isinstance(section.get("items"), list) else []
    return {
        "section_type": str(section.get("section_type") or ""),
        "title": str(section.get("title") or ""),
        "items": [_section_item(item) for item in items],
    }


def _section_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = (
        "case_id",
        "trade_date",
        "asset_id",
        "theme",
        "title",
        "review_status",
        "gap_reasons",
        "gap_summary",
        "case_count",
        "claim_count",
        "evidence_count",
        "evidence_link_count",
        "gap_count",
        "pending_gap_count",
        "reviewed_gap_count",
    )
    clean: dict[str, Any] = {}
    for key in allowed:
        if key not in value:
            continue
        if key == "gap_reasons":
            clean[key] = [str(item) for item in value.get(key) or []]
        elif key.endswith("_count") or key in {"evidence_count", "evidence_link_count", "gap_count", "claim_count"}:
            clean[key] = _int(value.get(key))
        else:
            clean[key] = str(value.get(key) or "")
    return clean


def _blocked_case_item(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    return {
        "case_id": str(item.get("case_id") or ""),
        "trade_date": str(item.get("trade_date") or ""),
        "asset_id": str(item.get("asset_id") or ""),
        "theme": str(item.get("theme") or ""),
        "title": str(item.get("title") or ""),
        "review_status": str(item.get("review_status") or ""),
        "gap_reasons": [str(reason) for reason in item.get("gap_reasons") or []],
        "gap_summary": str(item.get("gap_summary") or ""),
    }


def _notice(value: Any) -> dict[str, Any]:
    notice = value if isinstance(value, dict) else {}
    return {
        "code": str(notice.get("code") or ""),
        "message": str(notice.get("message") or ""),
        "count": _int(notice.get("count")),
    }


def _preview_markdown(package: dict[str, Any]) -> str:
    summary = package["summary"]
    blockers = package["blockers"]
    lines = [
        f"# Research Publication Preview {package['trade_date']}",
        "",
        f"- package_id={package['package_id']}",
        f"- publishable={str(package['publishable']).lower()}",
        f"- actual_publish_enabled={str(package['actual_publish_enabled']).lower()}",
        f"- gate_status={package['gate']['status']}",
        f"- case_count={summary['case_count']}",
        f"- claim_count={summary['claim_count']}",
        f"- gap_count={summary['gap_count']}",
        "",
        "## Blockers",
    ]
    if blockers:
        lines.extend(f"- {item['code']}: {item['message']} ({item['count']})" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("This is a dry-run preview only. It does not publish, send notifications, or write publication snapshots.")
    return "\n".join(lines) + "\n"


def _entrypoint_lock_report() -> str:
    return """# Research Publication Entrypoint Lock Report

Generated: 2026-07-08

## Candidate classification

| Category | Candidate | Entry point | External side effect | Guard / dry-run | Snapshot fit |
| --- | --- | --- | --- | --- | --- |
| A. read-only dashboard display | dashboard readiness / queue health / publish gate APIs | `src/stock_research/dashboard/app.py` read routes | No | No write token needed | No, read-only surface |
| B. preview / dry-run | research publication preview | `stock-research research-publication-preview`, `/api/research/publication/preview` | No | Dry-run only | No, preview only |
| C. strategy EOD publish | strategy EOD artifact publish | `src/stock_research/strategy_eod_publish.py::publish_strategy_eod` | Writes artifacts and manifest rows | CLI controlled, not research queue scoped | Maybe strategy snapshot, not research queue publication |
| D. downstream notification delivery | P5 notification and report delivery | `src/stock_research/p5/notifications.py`, `report-delivery-feishu-send`, `report-delivery-openclaw-send` | Can send network messages when live flags are enabled | dry-run / allow-live-send flags | No, downstream delivery is too late |
| E. true external/public release candidate | Not locked | Not yet identified | Unknown | Must call research publish gate before release | Future canonical write point |
| F. unrelated/legacy/test-only | research scripts and test fixtures | `scripts/run_*.py`, tests | Mixed, mostly local artifacts | Script-specific | No |

## Canonical recommendation

Do not use `p5/notifications.py` as the canonical research publish entrypoint. It is a downstream delivery layer and includes live sender capabilities. A publication snapshot written there would miss the actual decision boundary.

Do not use `strategy_eod_publish.py` directly as the research queue publication entrypoint. It publishes strategy EOD artifacts and manifest rows, and it should remain separate from research queue publication.

The canonical research publish entrypoint should be a future, explicit research-queue-scoped command/API that:

1. calls the internal research publish gate before release,
2. builds the research publication package,
3. writes `research.publication_snapshot` at the decision boundary,
4. then hands off to downstream delivery if needed.

## Future insertion points

- Publish gate check: immediately before the canonical research queue release decision.
- `publication_snapshot` write: in the same canonical entrypoint, before downstream notifications.
- Downstream notifications: after the snapshot write succeeds.

## Manual confirmations still needed

- Exact human owner of research queue publication.
- Whether a publish package can exclude deferred cases.
- Final external destination and delivery channel.
- Whether research queue publication is distinct from strategy EOD public artifacts in operations.
"""


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
