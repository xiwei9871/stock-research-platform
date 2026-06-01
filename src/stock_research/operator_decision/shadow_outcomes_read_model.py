from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_outcome_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator shadow outcome review must be a JSON object: {json_path}")

    _validate_safety_fields(review)

    run_id = str(review.get("run_id") or "")
    review_date = str(review.get("review_date") or "")
    if not run_id:
        raise ValueError(f"operator shadow outcome review requires run_id: {json_path}")
    if not review_date:
        raise ValueError(f"operator shadow outcome review requires review_date: {json_path}")

    outcomes = [item for item in review.get("outcomes", []) if isinstance(item, dict)]
    details_csv_path, markdown_path = _artifact_paths(json_path)
    return {
        "run": {
            "run_id": run_id,
            "review_date": review_date,
            "status": str(review.get("status") or ""),
            "outcome_count": int(review.get("outcome_count") or len(outcomes)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "details_csv_path": str(details_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {"horizons": review.get("horizons") or []},
        },
        "candidates": [
            _candidate_row(item, run_id=run_id, outcome_artifact_path=json_path)
            for item in outcomes
        ],
    }


def import_shadow_outcome_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _review_paths(input_path)
    run_ids: list[str] = []
    candidate_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for review_path in paths:
                rows = load_shadow_outcome_read_model_rows(review_path)
                _upsert_run(cur, rows["run"])
                for candidate in rows["candidates"]:
                    _upsert_candidate(cur, candidate)
                    candidate_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "candidate_count": candidate_count,
        "run_ids": run_ids,
    }


def _review_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_outcomes_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_outcome_run (
        run_id, review_date, status, outcome_count, manual_review_required,
        auto_trade_enabled, production_watchlist_enabled, production_write_enabled,
        json_path, details_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_date)s, %(status)s, %(outcome_count)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(json_path)s, %(details_csv_path)s, %(markdown_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_date = EXCLUDED.review_date,
        status = EXCLUDED.status,
        outcome_count = EXCLUDED.outcome_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        json_path = EXCLUDED.json_path,
        details_csv_path = EXCLUDED.details_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(sql, {**row, "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True)})


def _upsert_candidate(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_outcome_candidate (
        shadow_outcome_id, run_id, shadow_candidate_id, source_p12_shadow_run_id,
        replay_result_id, source_p11_replay_run_id, source_p10_proposal_run_id,
        source_p9_analytics_run_id, candidate_date, asset_id, stock_code,
        stock_name, shadow_layer, shadow_status, candidate_reason, outcome_status,
        available_future_bars, base_trade_date, base_close, forward_returns,
        max_high_returns, max_low_drawdowns, source_shadow_artifact_path,
        outcome_artifact_path, manual_review_required, auto_trade_enabled,
        production_watchlist_enabled, production_write_enabled, metadata
    )
    VALUES (
        %(shadow_outcome_id)s, %(run_id)s, %(shadow_candidate_id)s,
        %(source_p12_shadow_run_id)s, %(replay_result_id)s,
        %(source_p11_replay_run_id)s, %(source_p10_proposal_run_id)s,
        %(source_p9_analytics_run_id)s, %(candidate_date)s, %(asset_id)s,
        %(stock_code)s, %(stock_name)s, %(shadow_layer)s, %(shadow_status)s,
        %(candidate_reason)s, %(outcome_status)s, %(available_future_bars)s,
        %(base_trade_date)s, %(base_close)s, %(forward_returns)s::jsonb,
        %(max_high_returns)s::jsonb, %(max_low_drawdowns)s::jsonb,
        %(source_shadow_artifact_path)s, %(outcome_artifact_path)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (shadow_outcome_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        shadow_candidate_id = EXCLUDED.shadow_candidate_id,
        source_p12_shadow_run_id = EXCLUDED.source_p12_shadow_run_id,
        replay_result_id = EXCLUDED.replay_result_id,
        source_p11_replay_run_id = EXCLUDED.source_p11_replay_run_id,
        source_p10_proposal_run_id = EXCLUDED.source_p10_proposal_run_id,
        source_p9_analytics_run_id = EXCLUDED.source_p9_analytics_run_id,
        candidate_date = EXCLUDED.candidate_date,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        shadow_layer = EXCLUDED.shadow_layer,
        shadow_status = EXCLUDED.shadow_status,
        candidate_reason = EXCLUDED.candidate_reason,
        outcome_status = EXCLUDED.outcome_status,
        available_future_bars = EXCLUDED.available_future_bars,
        base_trade_date = EXCLUDED.base_trade_date,
        base_close = EXCLUDED.base_close,
        forward_returns = EXCLUDED.forward_returns,
        max_high_returns = EXCLUDED.max_high_returns,
        max_low_drawdowns = EXCLUDED.max_low_drawdowns,
        source_shadow_artifact_path = EXCLUDED.source_shadow_artifact_path,
        outcome_artifact_path = EXCLUDED.outcome_artifact_path,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "forward_returns": json.dumps(row.get("forward_returns") or {}, sort_keys=True),
            "max_high_returns": json.dumps(row.get("max_high_returns") or {}, sort_keys=True),
            "max_low_drawdowns": json.dumps(row.get("max_low_drawdowns") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _candidate_row(
    item: dict[str, Any],
    *,
    run_id: str,
    outcome_artifact_path: Path,
) -> dict[str, Any]:
    _validate_safety_fields(item)

    shadow_candidate_id = _required_text(item, "shadow_candidate_id")
    source_shadow_artifact_path = str(item.get("source_shadow_artifact_path") or "")
    outcome_artifact = str(item.get("outcome_artifact_path") or outcome_artifact_path)
    return {
        "shadow_outcome_id": _resolved_shadow_outcome_id(
            item.get("shadow_outcome_id"),
            run_id=run_id,
            shadow_candidate_id=shadow_candidate_id,
        ),
        "run_id": run_id,
        "shadow_candidate_id": shadow_candidate_id,
        "source_p12_shadow_run_id": _required_text(item, "source_p12_shadow_run_id"),
        "replay_result_id": _required_text(item, "replay_result_id"),
        "source_p11_replay_run_id": _required_text(item, "source_p11_replay_run_id"),
        "source_p10_proposal_run_id": _required_text(item, "source_p10_proposal_run_id"),
        "source_p9_analytics_run_id": _required_text(item, "source_p9_analytics_run_id"),
        "candidate_date": _required_text(item, "candidate_date"),
        "asset_id": _required_text(item, "asset_id"),
        "stock_code": str(item.get("stock_code") or ""),
        "stock_name": str(item.get("stock_name") or ""),
        "shadow_layer": _required_text(item, "shadow_layer"),
        "shadow_status": str(item.get("shadow_status") or item.get("status") or ""),
        "candidate_reason": str(item.get("candidate_reason") or ""),
        "outcome_status": _required_text(item, "outcome_status"),
        "available_future_bars": int(item.get("available_future_bars") or 0),
        "base_trade_date": str(item.get("base_trade_date") or ""),
        "base_close": item.get("base_close"),
        "forward_returns": _metric_map(item, "forward_", "d_return"),
        "max_high_returns": _metric_map(item, "max_high_return_", "d"),
        "max_low_drawdowns": _metric_map(item, "max_low_drawdown_", "d"),
        "source_shadow_artifact_path": source_shadow_artifact_path,
        "outcome_artifact_path": outcome_artifact,
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "metadata": _metadata(item),
    }


def _validate_safety_fields(item: dict[str, Any]) -> None:
    manual_review_required = _parse_safety_value(
        item.get("manual_review_required"),
        column="manual_review_required",
        default=True,
    )
    auto_trade_enabled = _parse_safety_value(
        item.get("auto_trade_enabled"),
        column="auto_trade_enabled",
        default=False,
    )
    production_watchlist_enabled = _parse_safety_value(
        item.get("production_watchlist_enabled"),
        column="production_watchlist_enabled",
        default=False,
    )
    production_write_enabled = _parse_safety_value(
        item.get("production_write_enabled"),
        column="production_write_enabled",
        default=False,
    )

    if auto_trade_enabled is True:
        raise ValueError("auto_trade_not_allowed")
    if manual_review_required is not True:
        raise ValueError("manual_review_required")
    if production_watchlist_enabled is True:
        raise ValueError("production_watchlist_not_allowed")
    if production_write_enabled is True:
        raise ValueError("production_write_not_allowed")


def _parse_safety_value(value: Any, *, column: str, default: bool) -> bool:
    if value is None:
        return default
    parsed = _bool_value(value)
    if parsed is None:
        raise ValueError(f"invalid_safety_field: {column}")
    return parsed


def _artifact_paths(json_path: Path) -> tuple[Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_details.csv"),
        json_path.with_suffix(".md"),
    )


def _required_text(item: dict[str, Any], column: str) -> str:
    value = item.get(column)
    if value is None or str(value).strip() == "":
        raise ValueError(f"required_field_missing: {column}")
    return str(value).strip()


def _metric_map(item: dict[str, Any], prefix: str, suffix: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key, value in item.items():
        text = str(key)
        if not text.startswith(prefix) or not text.endswith(suffix):
            continue
        horizon = text.removeprefix(prefix).removesuffix(suffix)
        if value is not None:
            metrics[horizon] = value
    return metrics


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "horizon_metrics": item.get("horizon_metrics") or {},
        "notes": item.get("notes") or "",
    }


def _resolved_shadow_outcome_id(value: Any, *, run_id: str, shadow_candidate_id: str) -> str:
    artifact_id = str(value or "")
    legacy_id = f"p13-shadow-outcome:{shadow_candidate_id}"
    if artifact_id and artifact_id != legacy_id:
        return artifact_id
    return _shadow_outcome_id(run_id=run_id, shadow_candidate_id=shadow_candidate_id)


def _shadow_outcome_id(*, run_id: str, shadow_candidate_id: str) -> str:
    raw = "|".join([run_id, shadow_candidate_id])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_outcome:{run_id}:{digest}"


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
