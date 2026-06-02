from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


EXPERIMENT_PROPOSAL_STATUSES = [
    "draft",
    "needs_more_data",
    "approved_for_experiment",
    "rejected",
    "deferred",
]

PROPOSAL_COLUMNS = [
    "proposal_id",
    "proposal_title",
    "hypothesis",
    "source_p9_analytics_run_id",
    "source_analytics_group_ids",
    "source_diagnostic_refs",
    "source_artifact_paths",
    "expected_validation_method",
    "risk_notes",
    "reviewer_id",
    "status",
    "manual_review_required",
    "auto_trade_enabled",
]

LIST_COLUMNS = [
    "source_analytics_group_ids",
    "source_diagnostic_refs",
    "source_artifact_paths",
]

REQUIRED_TEXT_COLUMNS = [
    "proposal_id",
    "proposal_title",
    "hypothesis",
    "source_p9_analytics_run_id",
    "expected_validation_method",
    "risk_notes",
    "reviewer_id",
    "status",
]

UNSAFE_EXECUTION_FIELDS = {
    "account_id",
    "broker",
    "broker_id",
    "cash",
    "execution_id",
    "fill_id",
    "limit_price",
    "notional",
    "order_id",
    "order_side",
    "position_id",
    "price",
    "quantity",
    "shares",
    "side",
    "stop_price",
    "trade_id",
}


def build_experiment_proposals_from_frames(*, proposal_events: pd.DataFrame) -> pd.DataFrame:
    _reject_unsafe_execution_fields(proposal_events)
    proposals = proposal_events.copy()
    for column in PROPOSAL_COLUMNS:
        if column not in proposals.columns:
            proposals[column] = _default_column_value(column)
    if proposals.empty:
        return pd.DataFrame(columns=PROPOSAL_COLUMNS)

    _normalize_safety_fields(proposals)
    for column in REQUIRED_TEXT_COLUMNS:
        proposals[column] = proposals[column].map(_required_text(column))
    for column in LIST_COLUMNS:
        proposals[column] = proposals[column].map(_list_value)

    invalid_statuses = sorted(set(proposals["status"]) - set(EXPERIMENT_PROPOSAL_STATUSES))
    if invalid_statuses:
        raise ValueError(f"invalid_proposal_status: {', '.join(invalid_statuses)}")

    missing_evidence = proposals.apply(
        lambda row: not row["source_analytics_group_ids"] and not row["source_diagnostic_refs"],
        axis=1,
    )
    if missing_evidence.any():
        missing_ids = ", ".join(proposals.loc[missing_evidence, "proposal_id"].astype(str).tolist())
        raise ValueError(f"source_evidence_required: {missing_ids}")
    missing_artifacts = proposals["source_artifact_paths"].map(lambda value: len(value) == 0)
    if missing_artifacts.any():
        missing_ids = ", ".join(proposals.loc[missing_artifacts, "proposal_id"].astype(str).tolist())
        raise ValueError(f"source_artifact_required: {missing_ids}")

    return proposals.loc[:, PROPOSAL_COLUMNS]


def build_experiment_proposal_review(
    *,
    proposal_events: pd.DataFrame,
    run_id: str | None = None,
    review_date: str | None = None,
) -> dict[str, Any]:
    proposals = build_experiment_proposals_from_frames(proposal_events=proposal_events)
    records = _records(proposals)
    status_counts = proposals["status"].value_counts().sort_index().to_dict() if not proposals.empty else {}
    return {
        "run_id": run_id or f"p10-experiment-proposals-{review_date or 'unknown-date'}",
        "review_date": str(review_date or ""),
        "status": "proposal_review_ready" if records else "no_proposals_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "promotion_enabled": False,
        "proposal_count": len(records),
        "status_counts": _json_safe(status_counts),
        "proposals": records,
    }


def write_experiment_proposal_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    review_date = _safe_path_part(review.get("review_date") or "unknown-date")
    stem = f"operator_experiment_proposals_{review_date}"

    json_path = output_path / f"{stem}.json"
    proposals_csv_path = output_path / f"{stem}_proposals.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(review)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload.get("proposals", []), columns=PROPOSAL_COLUMNS).to_csv(proposals_csv_path, index=False)
    markdown_path.write_text(_render_proposal_review_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "proposals_csv_path": str(proposals_csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_safety_fields(proposals: pd.DataFrame) -> None:
    proposals["manual_review_required"] = proposals["manual_review_required"].map(
        lambda value: True if _is_missing(value) else _bool_value(value)
    )
    if proposals["manual_review_required"].ne(True).any():
        raise ValueError("manual_review_required")

    proposals["auto_trade_enabled"] = proposals["auto_trade_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if proposals["auto_trade_enabled"].eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    proposals["auto_trade_enabled"] = False


def _reject_unsafe_execution_fields(events: pd.DataFrame) -> None:
    for column in events.columns:
        normalized_column = str(column).strip().lower()
        if normalized_column not in UNSAFE_EXECUTION_FIELDS:
            continue
        if events[column].map(lambda value: not _is_missing(value) and str(value).strip() != "").any():
            raise ValueError(f"unsafe_execution_field: {column}")


def _required_text(column: str):
    def normalize(value: Any) -> str:
        if _is_missing(value) or str(value).strip() == "":
            raise ValueError(f"required_field_missing: {column}")
        return str(value).strip()

    return normalize


def _list_value(value: Any) -> list[str]:
    if _is_missing(value):
        return []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if not _is_missing(item) and str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("list_field_must_be_array")
        return [str(item).strip() for item in parsed if not _is_missing(item) and str(item).strip()]
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _default_column_value(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column == "auto_trade_enabled":
        return False
    if column in LIST_COLUMNS:
        return []
    return ""


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_json_safe(record) for record in frame.to_dict("records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _render_proposal_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P10 Experiment Proposal Review",
        "",
        f"- run_id: {_markdown_cell(review.get('run_id'))}",
        f"- review_date: {_markdown_cell(review.get('review_date'))}",
        f"- status: {_markdown_cell(review.get('status'))}",
        "- manual_review_required: true",
        "- auto_trade_enabled: false",
        "- promotion_enabled: false",
        "",
        "Review-only experiment governance. No score, watchlist, broker, order, or execution state is modified.",
        "",
        "## Summary",
        "",
        f"- proposal_count: {int(review.get('proposal_count') or 0)}",
        "",
        "## Proposals",
        "",
    ]
    proposals = review.get("proposals") or []
    if not proposals:
        lines.append("No experiment proposals recorded.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Proposal | Status | Reviewer | Source Run | Validation |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in proposals:
        lines.append(
            " | ".join(
                [
                    f"| {_markdown_cell(row.get('proposal_id'))}",
                    _markdown_cell(row.get("status")),
                    _markdown_cell(row.get("reviewer_id")),
                    _markdown_cell(row.get("source_p9_analytics_run_id")),
                    f"{_markdown_cell(row.get('expected_validation_method'))} |",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _safe_path_part(value: Any) -> str:
    text = str(value or "")
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in text)


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
