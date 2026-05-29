from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DECISION_LABELS = {"observe", "candidate", "caution", "remove", "no_action"}

DECISION_JOURNAL_COLUMNS = [
    "review_date",
    "review_session_id",
    "reviewer_id",
    "asset_id",
    "stock_code",
    "stock_name",
    "decision_label",
    "evidence_artifact_id",
    "evidence_path",
    "source_context",
    "requires_follow_up",
    "follow_up_note",
    "manual_review_required",
    "auto_trade_enabled",
    "notes",
]

REQUIRED_EVENT_FIELDS = [
    "review_date",
    "review_session_id",
    "asset_id",
    "decision_label",
    "requires_follow_up",
    "manual_review_required",
    "auto_trade_enabled",
]

EXECUTION_FIELD_NAMES = {
    "account_id",
    "broker",
    "broker_account",
    "cash",
    "execution_id",
    "execution_status",
    "filled_quantity",
    "order_id",
    "order_status",
    "submitted_at",
}


def build_decision_journal(
    *,
    review_date: str,
    review_session_id: str,
    reviewer_id: str,
    source_artifact_root: str,
    events: pd.DataFrame,
) -> dict[str, Any]:
    issues = validate_decision_events(events)
    if issues:
        issue_codes = ", ".join(sorted({str(issue["code"]) for issue in issues}))
        raise ValueError(f"invalid decision journal events: {issue_codes}")

    normalized = _normalize_events(
        review_date=review_date,
        review_session_id=review_session_id,
        reviewer_id=reviewer_id,
        events=events,
    )
    items = normalized.to_dict("records")
    label_counts = (
        normalized["decision_label"].astype(str).value_counts().sort_index().to_dict()
        if not normalized.empty
        else {}
    )
    return {
        "review_date": review_date,
        "review_session_id": review_session_id,
        "reviewer_id": reviewer_id,
        "source_artifact_root": source_artifact_root,
        "status": "review_recorded" if items else "no_decisions_recorded",
        "decision_count": int(len(items)),
        "decision_label_counts": {str(key): int(value) for key, value in label_counts.items()},
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "issues": [],
        "items": items,
    }


def validate_decision_events(events: pd.DataFrame) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if events.empty:
        return issues

    execution_columns = sorted(set(events.columns) & EXECUTION_FIELD_NAMES)
    for column in execution_columns:
        issues.append(
            {
                "code": "execution_field_not_allowed",
                "severity": "blocker",
                "row_index": None,
                "field": column,
                "message": f"execution field is not allowed in operator decisions: {column}",
            }
        )

    for field in REQUIRED_EVENT_FIELDS:
        if field not in events.columns:
            issues.append(
                {
                    "code": "missing_required_field",
                    "severity": "blocker",
                    "row_index": None,
                    "field": field,
                    "message": f"missing required decision field: {field}",
                }
            )

    if issues and any(issue["code"] == "missing_required_field" for issue in issues):
        return issues

    for index, row in events.reset_index(drop=True).iterrows():
        label = str(row.get("decision_label", "")).strip()
        if label not in DECISION_LABELS:
            issues.append(
                {
                    "code": "invalid_decision_label",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": f"invalid decision_label: {label}",
                }
            )
        evidence_artifact_id = str(row.get("evidence_artifact_id", "")).strip()
        evidence_path = str(row.get("evidence_path", "")).strip()
        if not evidence_artifact_id and not evidence_path:
            issues.append(
                {
                    "code": "missing_evidence",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "decision events must cite an evidence artifact or path",
                }
            )
        if _bool_value(row.get("manual_review_required")) is not True:
            issues.append(
                {
                    "code": "manual_review_required",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "manual_review_required must be true",
                }
            )
        if _bool_value(row.get("auto_trade_enabled")) is not False:
            issues.append(
                {
                    "code": "auto_trade_not_allowed",
                    "severity": "blocker",
                    "row_index": int(index),
                    "message": "auto_trade_enabled must remain false",
                }
            )
    return issues


def write_decision_journal(journal: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    review_date = str(journal["review_date"])
    review_session_id = _safe_stem(str(journal["review_session_id"]))
    stem = f"operator_decision_journal_{review_date}_{review_session_id}"
    json_path = output_path / f"{stem}.json"
    csv_path = output_path / f"{stem}.csv"
    markdown_path = output_path / f"{stem}.md"

    json_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(journal.get("items", []), columns=DECISION_JOURNAL_COLUMNS).to_csv(csv_path, index=False)
    markdown_path.write_text(_render_markdown(journal), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_events(
    *,
    review_date: str,
    review_session_id: str,
    reviewer_id: str,
    events: pd.DataFrame,
) -> pd.DataFrame:
    normalized = events.copy()
    for column in DECISION_JOURNAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized = normalized[DECISION_JOURNAL_COLUMNS].copy()
    normalized["review_date"] = normalized["review_date"].replace("", review_date).fillna(review_date)
    normalized["review_session_id"] = (
        normalized["review_session_id"].replace("", review_session_id).fillna(review_session_id)
    )
    normalized["reviewer_id"] = normalized["reviewer_id"].replace("", reviewer_id).fillna(reviewer_id)
    normalized["decision_label"] = normalized["decision_label"].astype(str).str.strip()
    normalized["requires_follow_up"] = normalized["requires_follow_up"].map(_bool_value)
    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    return normalized


def _render_markdown(journal: dict[str, Any]) -> str:
    lines = [
        f"# Operator Decision Journal {journal['review_date']}",
        "",
        "Review-only decision record. No broker, order, account, cash, or execution state is modified.",
        "",
        f"- review_session_id: `{journal['review_session_id']}`",
        f"- reviewer_id: `{journal['reviewer_id']}`",
        f"- status: `{journal['status']}`",
        f"- decision_count: `{journal['decision_count']}`",
        f"- manual_review_required: `{journal['manual_review_required']}`",
        f"- auto_trade_enabled: `{journal['auto_trade_enabled']}`",
        "",
    ]
    items = journal.get("items", [])
    if not items:
        lines.append("No decisions recorded.")
    else:
        lines.append("| Asset | Decision | Evidence | Follow Up |")
        lines.append("| --- | --- | --- | --- |")
        for item in items:
            follow_up = "yes" if bool(item.get("requires_follow_up")) else "no"
            evidence = str(item.get("evidence_artifact_id") or item.get("evidence_path") or "")
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("asset_id", "")),
                        str(item.get("decision_label", "")),
                        evidence,
                        follow_up,
                    ]
                )
                + " |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _safe_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:80]
