from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


SHADOW_WATCHLIST_STATUSES = [
    "shadow_ready",
    "shadow_observe",
    "shadow_rejected",
    "needs_more_data",
    "blocked",
]

SHADOW_COLUMNS = [
    "shadow_candidate_id",
    "replay_result_id",
    "source_p11_replay_run_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "candidate_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "shadow_layer",
    "candidate_reason",
    "evidence_artifact_paths",
    "metric_summary",
    "reviewer_id",
    "status",
    "review_notes",
    "manual_review_required",
    "auto_trade_enabled",
    "production_watchlist_enabled",
    "production_write_enabled",
]

REQUIRED_TEXT_COLUMNS = [
    "shadow_candidate_id",
    "replay_result_id",
    "source_p11_replay_run_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "candidate_date",
    "asset_id",
    "shadow_layer",
    "candidate_reason",
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


def build_shadow_watchlist_candidates_from_frames(
    *,
    replay_results: pd.DataFrame,
    candidate_events: pd.DataFrame,
) -> pd.DataFrame:
    _reject_unsafe_execution_fields(candidate_events)
    replay_lookup = _normalize_replay_results(replay_results)
    candidates = candidate_events.copy()
    for column in SHADOW_COLUMNS:
        if column not in candidates.columns:
            candidates[column] = _default_column_value(column)
    if candidates.empty:
        return pd.DataFrame(columns=SHADOW_COLUMNS)

    _normalize_safety_fields(candidates)
    for column in REQUIRED_TEXT_COLUMNS:
        candidates[column] = candidates[column].map(_required_text(column))
    for column in ["stock_code", "stock_name", "review_notes"]:
        candidates[column] = candidates[column].fillna("").astype(str)
    candidates["evidence_artifact_paths"] = candidates["evidence_artifact_paths"].map(_list_value)
    candidates["metric_summary"] = candidates["metric_summary"].map(_dict_value)

    invalid_statuses = sorted(set(candidates["status"]) - set(SHADOW_WATCHLIST_STATUSES))
    if invalid_statuses:
        raise ValueError(f"invalid_shadow_status: {', '.join(invalid_statuses)}")

    missing_evidence = candidates["evidence_artifact_paths"].map(lambda value: len(value) == 0)
    if missing_evidence.any():
        missing_ids = ", ".join(candidates.loc[missing_evidence, "shadow_candidate_id"].astype(str).tolist())
        raise ValueError(f"evidence_artifact_required: {missing_ids}")

    _validate_against_replay(candidates, replay_lookup)
    return candidates.loc[:, SHADOW_COLUMNS]


def build_shadow_watchlist_review(
    *,
    replay_results: pd.DataFrame,
    candidate_events: pd.DataFrame,
    run_id: str | None = None,
    review_date: str | None = None,
) -> dict[str, Any]:
    candidates = build_shadow_watchlist_candidates_from_frames(
        replay_results=replay_results,
        candidate_events=candidate_events,
    )
    records = _records(candidates)
    status_counts = candidates["status"].value_counts().sort_index().to_dict() if not candidates.empty else {}
    date_text = str(review_date or "")
    return {
        "run_id": run_id or f"p12-shadow-watchlist-{date_text}",
        "review_date": date_text,
        "status": "shadow_watchlist_review_ready" if records else "no_shadow_candidates_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "candidate_count": len(records),
        "status_counts": _json_safe(status_counts),
        "candidates": records,
    }


def write_shadow_watchlist_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    review_date = _safe_path_part(review.get("review_date") or "unknown-date")
    stem = f"operator_shadow_watchlist_{review_date}"

    json_path = output_path / f"{stem}.json"
    candidates_csv_path = output_path / f"{stem}_candidates.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(review)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload.get("candidates", []), columns=SHADOW_COLUMNS).to_csv(candidates_csv_path, index=False)
    markdown_path.write_text(_render_shadow_watchlist_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "candidates_csv_path": str(candidates_csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_replay_results(replay_results: pd.DataFrame) -> dict[str, dict[str, Any]]:
    replay = replay_results.copy()
    for column in [
        "replay_result_id",
        "run_id",
        "source_p10_proposal_run_id",
        "source_p9_analytics_run_id",
        "replay_status",
        "manual_review_required",
        "auto_trade_enabled",
        "production_write_enabled",
    ]:
        if column not in replay.columns:
            replay[column] = _default_replay_column_value(column)
    if replay.empty:
        return {}
    for column in ["replay_result_id", "run_id", "source_p10_proposal_run_id", "source_p9_analytics_run_id", "replay_status"]:
        replay[column] = replay[column].fillna("").astype(str)
    replay["manual_review_required"] = replay["manual_review_required"].map(
        lambda value: True if _is_missing(value) else _bool_value(value)
    )
    if replay["manual_review_required"].ne(True).any():
        raise ValueError("manual_review_required")
    replay["auto_trade_enabled"] = replay["auto_trade_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if replay["auto_trade_enabled"].eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    replay["production_write_enabled"] = replay["production_write_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if replay["production_write_enabled"].eq(True).any():
        raise ValueError("production_write_not_allowed")
    return {str(row["replay_result_id"]): row for row in replay.to_dict("records")}


def _validate_against_replay(candidates: pd.DataFrame, replay_lookup: dict[str, dict[str, Any]]) -> None:
    for row in candidates.to_dict("records"):
        replay_result_id = str(row["replay_result_id"])
        replay = replay_lookup.get(replay_result_id)
        if replay is None:
            raise ValueError(f"replay_result_not_found: {replay_result_id}")
        if replay.get("replay_status") != "passed_offline_replay":
            raise ValueError(f"replay_not_passed_offline: {replay_result_id}")
        if str(row["source_p11_replay_run_id"]) != str(replay.get("run_id")):
            raise ValueError(f"source_p11_replay_run_mismatch: {replay_result_id}")
        if str(row["source_p10_proposal_run_id"]) != str(replay.get("source_p10_proposal_run_id")):
            raise ValueError(f"source_p10_proposal_run_mismatch: {replay_result_id}")
        if str(row["source_p9_analytics_run_id"]) != str(replay.get("source_p9_analytics_run_id")):
            raise ValueError(f"source_p9_analytics_run_mismatch: {replay_result_id}")


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

    frame["production_watchlist_enabled"] = frame["production_watchlist_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if frame["production_watchlist_enabled"].eq(True).any():
        raise ValueError("production_watchlist_not_allowed")
    frame["production_watchlist_enabled"] = False

    frame["production_write_enabled"] = frame["production_write_enabled"].map(
        lambda value: False if _is_missing(value) else _bool_value(value)
    )
    if frame["production_write_enabled"].eq(True).any():
        raise ValueError("production_write_not_allowed")
    frame["production_write_enabled"] = False

    for column in [
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]:
        frame[column] = frame[column].map(bool).astype(object)


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
    if isinstance(value, (list, tuple, set)):
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
    if column in {"auto_trade_enabled", "production_watchlist_enabled", "production_write_enabled"}:
        return False
    if column == "evidence_artifact_paths":
        return []
    if column == "metric_summary":
        return {}
    return ""


def _default_replay_column_value(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column in {"auto_trade_enabled", "production_write_enabled"}:
        return False
    return ""


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_json_safe(record) for record in frame.to_dict("records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if _is_missing(value):
        return None
    return value


def _safe_path_part(value: Any) -> str:
    return str(value).replace("/", "-").replace(":", "-")


def _render_shadow_watchlist_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P12 Shadow Watchlist Review",
        "",
        f"run_id: {review.get('run_id', '')}",
        f"review_date: {review.get('review_date', '')}",
        f"status: {review.get('status', '')}",
        f"candidate_count: {review.get('candidate_count', 0)}",
        f"manual_review_required: {str(review.get('manual_review_required', True)).lower()}",
        f"auto_trade_enabled: {str(review.get('auto_trade_enabled', False)).lower()}",
        f"production_watchlist_enabled: {str(review.get('production_watchlist_enabled', False)).lower()}",
        f"production_write_enabled: {str(review.get('production_write_enabled', False)).lower()}",
        "",
        "## Candidates",
    ]
    for candidate in review.get("candidates", []):
        lines.extend(
            [
                "",
                f"- {candidate.get('shadow_candidate_id', '')} | {candidate.get('asset_id', '')} | {candidate.get('status', '')}",
                f"  - replay_result_id: {candidate.get('replay_result_id', '')}",
                f"  - source_p10_proposal_run_id: {candidate.get('source_p10_proposal_run_id', '')}",
                f"  - source_p9_analytics_run_id: {candidate.get('source_p9_analytics_run_id', '')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
