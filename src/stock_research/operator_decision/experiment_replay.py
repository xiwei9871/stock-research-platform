from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


EXPERIMENT_REPLAY_STATUSES = [
    "replay_ready",
    "passed_offline_replay",
    "failed_offline_replay",
    "needs_more_data",
    "blocked",
]

REPLAY_COLUMNS = [
    "replay_result_id",
    "proposal_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "replay_start_date",
    "replay_end_date",
    "replay_input_artifact_paths",
    "validation_method",
    "replay_status",
    "sample_count",
    "passed_count",
    "failed_count",
    "metric_summary",
    "failure_reason",
    "defer_reason",
    "manual_review_required",
    "auto_trade_enabled",
    "production_write_enabled",
]

REQUIRED_TEXT_COLUMNS = [
    "replay_result_id",
    "proposal_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "replay_start_date",
    "replay_end_date",
    "validation_method",
    "replay_status",
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


def build_experiment_replay_results_from_frames(
    *,
    proposals: pd.DataFrame,
    replay_events: pd.DataFrame,
) -> pd.DataFrame:
    _reject_unsafe_execution_fields(replay_events)
    normalized_proposals = _normalize_proposals(proposals)
    replay = replay_events.copy()
    for column in REPLAY_COLUMNS:
        if column not in replay.columns:
            replay[column] = _default_column_value(column)
    if replay.empty:
        return pd.DataFrame(columns=REPLAY_COLUMNS)

    _normalize_safety_fields(replay)
    for column in REQUIRED_TEXT_COLUMNS:
        replay[column] = replay[column].map(_required_text(column))

    replay["replay_input_artifact_paths"] = replay["replay_input_artifact_paths"].map(_list_value)
    replay["metric_summary"] = replay["metric_summary"].map(_dict_value)
    for column in ["sample_count", "passed_count", "failed_count"]:
        replay[column] = replay[column].fillna(0).astype(int)
    replay["failure_reason"] = replay["failure_reason"].fillna("").astype(str)
    replay["defer_reason"] = replay["defer_reason"].fillna("").astype(str)

    invalid_statuses = sorted(set(replay["replay_status"]) - set(EXPERIMENT_REPLAY_STATUSES))
    if invalid_statuses:
        raise ValueError(f"invalid_replay_status: {', '.join(invalid_statuses)}")

    _validate_against_proposals(replay, normalized_proposals)
    missing_inputs = replay["replay_input_artifact_paths"].map(lambda value: len(value) == 0)
    if missing_inputs.any():
        missing_ids = ", ".join(replay.loc[missing_inputs, "replay_result_id"].astype(str).tolist())
        raise ValueError(f"replay_input_artifact_required: {missing_ids}")

    return replay.loc[:, REPLAY_COLUMNS]


def build_experiment_replay_review(
    *,
    proposals: pd.DataFrame,
    replay_events: pd.DataFrame,
    run_id: str | None = None,
    replay_start_date: str | None = None,
    replay_end_date: str | None = None,
) -> dict[str, Any]:
    results = build_experiment_replay_results_from_frames(
        proposals=proposals,
        replay_events=replay_events,
    )
    records = _records(results)
    status_counts = results["replay_status"].value_counts().sort_index().to_dict() if not results.empty else {}
    start_date = str(replay_start_date or "")
    end_date = str(replay_end_date or "")
    return {
        "run_id": run_id or f"p11-experiment-replay-{start_date}-{end_date}",
        "replay_start_date": start_date,
        "replay_end_date": end_date,
        "status": "replay_review_ready" if records else "no_replay_results_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_write_enabled": False,
        "result_count": len(records),
        "status_counts": _json_safe(status_counts),
        "results": records,
    }


def write_experiment_replay_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    start_date = _safe_path_part(review.get("replay_start_date") or "unknown-start")
    end_date = _safe_path_part(review.get("replay_end_date") or "unknown-end")
    stem = f"operator_experiment_replay_{start_date}_{end_date}"

    json_path = output_path / f"{stem}.json"
    results_csv_path = output_path / f"{stem}_results.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(review)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload.get("results", []), columns=REPLAY_COLUMNS).to_csv(results_csv_path, index=False)
    markdown_path.write_text(_render_replay_review_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "results_csv_path": str(results_csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_proposals(proposals: pd.DataFrame) -> pd.DataFrame:
    normalized = proposals.copy()
    for column in [
        "proposal_id",
        "run_id",
        "source_p9_analytics_run_id",
        "source_analytics_group_ids",
        "source_diagnostic_refs",
        "source_artifact_paths",
        "status",
        "manual_review_required",
        "auto_trade_enabled",
        "promotion_enabled",
    ]:
        if column not in normalized.columns:
            normalized[column] = _proposal_default(column)
    if normalized.empty:
        return normalized
    for column in ["proposal_id", "run_id", "source_p9_analytics_run_id", "status"]:
        normalized[column] = normalized[column].fillna("").astype(str)
    for column in ["source_analytics_group_ids", "source_diagnostic_refs", "source_artifact_paths"]:
        normalized[column] = normalized[column].map(_list_value)
    _normalize_proposal_safety_fields(normalized)
    return normalized


def _validate_against_proposals(replay: pd.DataFrame, proposals: pd.DataFrame) -> None:
    proposal_lookup = {str(row["proposal_id"]): row for row in proposals.to_dict("records")}
    for row in replay.to_dict("records"):
        proposal_id = str(row["proposal_id"])
        proposal = proposal_lookup.get(proposal_id)
        if proposal is None:
            raise ValueError(f"proposal_not_found: {proposal_id}")
        if proposal.get("status") != "approved_for_experiment":
            raise ValueError(f"proposal_not_approved_for_experiment: {proposal_id}")
        if str(row["source_p10_proposal_run_id"]) != str(proposal.get("run_id")):
            raise ValueError(f"source_p10_proposal_run_mismatch: {proposal_id}")
        if str(row["source_p9_analytics_run_id"]) != str(proposal.get("source_p9_analytics_run_id")):
            raise ValueError(f"source_p9_analytics_run_mismatch: {proposal_id}")
        if not proposal.get("source_analytics_group_ids") and not proposal.get("source_diagnostic_refs"):
            raise ValueError(f"source_evidence_required: {proposal_id}")
        if not proposal.get("source_artifact_paths"):
            raise ValueError(f"source_artifact_required: {proposal_id}")


def _normalize_safety_fields(frame: pd.DataFrame) -> None:
    frame["manual_review_required"] = frame["manual_review_required"].map(
        lambda value: True if _is_missing(value) else _bool_value(value)
    )
    if frame["manual_review_required"].ne(True).any():
        raise ValueError("manual_review_required")

    frame["auto_trade_enabled"] = frame["auto_trade_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if frame["auto_trade_enabled"].eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    frame["auto_trade_enabled"] = False

    frame["production_write_enabled"] = frame["production_write_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if frame["production_write_enabled"].eq(True).any():
        raise ValueError("production_write_not_allowed")
    frame["production_write_enabled"] = False
    for column in ["manual_review_required", "auto_trade_enabled", "production_write_enabled"]:
        frame[column] = frame[column].map(bool).astype(object)


def _normalize_proposal_safety_fields(proposals: pd.DataFrame) -> None:
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
    proposals["promotion_enabled"] = proposals["promotion_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if proposals["promotion_enabled"].eq(True).any():
        raise ValueError("promotion_not_allowed")
    for column in ["manual_review_required", "auto_trade_enabled", "promotion_enabled"]:
        proposals[column] = proposals[column].map(bool).astype(object)


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


def _dict_value(value: Any) -> dict[str, Any]:
    if _is_missing(value):
        return {}
    if isinstance(value, dict):
        return _json_safe(value)
    text = str(value).strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("metric_summary_must_be_object")
    return _json_safe(parsed)


def _default_column_value(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column in {"auto_trade_enabled", "production_write_enabled"}:
        return False
    if column == "replay_input_artifact_paths":
        return []
    if column == "metric_summary":
        return {}
    if column in {"sample_count", "passed_count", "failed_count"}:
        return 0
    return ""


def _proposal_default(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column in {"auto_trade_enabled", "promotion_enabled"}:
        return False
    if column in {"source_analytics_group_ids", "source_diagnostic_refs", "source_artifact_paths"}:
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


def _render_replay_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P11 Experiment Replay Review",
        "",
        f"- run_id: {_markdown_cell(review.get('run_id'))}",
        f"- replay_start_date: {_markdown_cell(review.get('replay_start_date'))}",
        f"- replay_end_date: {_markdown_cell(review.get('replay_end_date'))}",
        f"- status: {_markdown_cell(review.get('status'))}",
        "- manual_review_required: true",
        "- auto_trade_enabled: false",
        "- production_write_enabled: false",
        "",
        "Offline replay only. No score, watchlist, broker, order, execution, or scheduler state is modified.",
        "",
        "## Summary",
        "",
        f"- result_count: {int(review.get('result_count') or 0)}",
        "",
        "## Replay Results",
        "",
    ]
    results = review.get("results") or []
    if not results:
        lines.append("No experiment replay results recorded.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Replay | Proposal | Status | Samples | Passed | Failed | Validation |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in results:
        lines.append(
            " | ".join(
                [
                    f"| {_markdown_cell(row.get('replay_result_id'))}",
                    _markdown_cell(row.get("proposal_id")),
                    _markdown_cell(row.get("replay_status")),
                    str(row.get("sample_count") or 0),
                    str(row.get("passed_count") or 0),
                    str(row.get("failed_count") or 0),
                    f"{_markdown_cell(row.get('validation_method'))} |",
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
