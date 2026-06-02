from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_decision_outcome_analytics_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    analytics = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(analytics, dict):
        raise ValueError(f"operator decision outcome analytics must be a JSON object: {json_path}")

    if _bool_value(analytics.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(analytics.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")

    run_id = str(analytics.get("run_id") or "")
    start_date = str(analytics.get("review_start_date") or "")
    end_date = str(analytics.get("review_end_date") or "")
    if not run_id:
        raise ValueError(f"operator decision outcome analytics requires run_id: {json_path}")
    if not start_date or not end_date:
        raise ValueError(f"operator decision outcome analytics requires review date range: {json_path}")

    groups_csv_path, diagnostics_csv_path, markdown_path = _artifact_paths(json_path)
    groups = [item for item in analytics.get("groups", []) if isinstance(item, dict)]
    horizons = [int(value) for value in analytics.get("horizons", [])]
    return {
        "run": {
            "run_id": run_id,
            "review_start_date": start_date,
            "review_end_date": end_date,
            "status": str(analytics.get("status") or ""),
            "source_outcome_count": int(analytics.get("source_outcome_count") or 0),
            "group_count": int(analytics.get("group_count") or len(groups)),
            "diagnostic_count": int(analytics.get("diagnostic_count") or len(analytics.get("diagnostics", []) or [])),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "json_path": str(json_path),
            "groups_csv_path": str(groups_csv_path),
            "diagnostics_csv_path": str(diagnostics_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {
                "horizons": horizons,
                "diagnostics": analytics.get("diagnostics") or [],
            },
        },
        "groups": [
            _group_row(
                item,
                run_id=run_id,
                review_start_date=start_date,
                review_end_date=end_date,
                horizons=horizons,
                analytics_artifact_path=json_path,
            )
            for item in groups
        ],
    }


def import_decision_outcome_analytics(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _analytics_paths(input_path)
    run_ids: list[str] = []
    group_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for analytics_path in paths:
                rows = load_decision_outcome_analytics_read_model_rows(analytics_path)
                _upsert_run(cur, rows["run"])
                for group in rows["groups"]:
                    _upsert_group(cur, group)
                    group_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "group_count": group_count,
        "run_ids": run_ids,
    }


def _analytics_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_decision_outcome_analytics_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_decision_outcome_analytics_run (
        run_id, review_start_date, review_end_date, status,
        source_outcome_count, group_count, diagnostic_count,
        manual_review_required, auto_trade_enabled, json_path,
        groups_csv_path, diagnostics_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_start_date)s, %(review_end_date)s, %(status)s,
        %(source_outcome_count)s, %(group_count)s, %(diagnostic_count)s,
        %(manual_review_required)s, %(auto_trade_enabled)s, %(json_path)s,
        %(groups_csv_path)s, %(diagnostics_csv_path)s, %(markdown_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        status = EXCLUDED.status,
        source_outcome_count = EXCLUDED.source_outcome_count,
        group_count = EXCLUDED.group_count,
        diagnostic_count = EXCLUDED.diagnostic_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        json_path = EXCLUDED.json_path,
        groups_csv_path = EXCLUDED.groups_csv_path,
        diagnostics_csv_path = EXCLUDED.diagnostics_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(sql, {**row, "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True)})


def _upsert_group(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_decision_outcome_analytics_group (
        analytics_group_id, run_id, review_start_date, review_end_date,
        analytics_level, group_value, decision_label, source_context,
        review_session_id, asset_id, sample_count, complete_count,
        insufficient_data_count, follow_up_required_rate, horizon_metrics,
        analytics_artifact_path, metadata
    )
    VALUES (
        %(analytics_group_id)s, %(run_id)s, %(review_start_date)s,
        %(review_end_date)s, %(analytics_level)s, %(group_value)s,
        %(decision_label)s, %(source_context)s, %(review_session_id)s,
        %(asset_id)s, %(sample_count)s, %(complete_count)s,
        %(insufficient_data_count)s, %(follow_up_required_rate)s,
        %(horizon_metrics)s::jsonb, %(analytics_artifact_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (analytics_group_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        analytics_level = EXCLUDED.analytics_level,
        group_value = EXCLUDED.group_value,
        decision_label = EXCLUDED.decision_label,
        source_context = EXCLUDED.source_context,
        review_session_id = EXCLUDED.review_session_id,
        asset_id = EXCLUDED.asset_id,
        sample_count = EXCLUDED.sample_count,
        complete_count = EXCLUDED.complete_count,
        insufficient_data_count = EXCLUDED.insufficient_data_count,
        follow_up_required_rate = EXCLUDED.follow_up_required_rate,
        horizon_metrics = EXCLUDED.horizon_metrics,
        analytics_artifact_path = EXCLUDED.analytics_artifact_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    params = {
        **row,
        "horizon_metrics": json.dumps(row.get("horizon_metrics") or {}, sort_keys=True),
        "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
    }
    cur.execute(sql, params)


def _group_row(
    item: dict[str, Any],
    *,
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    horizons: list[int],
    analytics_artifact_path: Path,
) -> dict[str, Any]:
    analytics_level = str(item.get("analytics_level") or "")
    group_value = str(item.get(analytics_level) or item.get("group_value") or "")
    return {
        "analytics_group_id": _analytics_group_id(
            run_id=run_id,
            analytics_level=analytics_level,
            group_value=group_value,
        ),
        "run_id": run_id,
        "review_start_date": review_start_date,
        "review_end_date": review_end_date,
        "analytics_level": analytics_level,
        "group_value": group_value,
        "decision_label": str(item.get("decision_label") or ""),
        "source_context": str(item.get("source_context") or ""),
        "review_session_id": str(item.get("review_session_id") or ""),
        "asset_id": str(item.get("asset_id") or ""),
        "sample_count": int(item.get("sample_count") or 0),
        "complete_count": int(item.get("complete_count") or 0),
        "insufficient_data_count": int(item.get("insufficient_data_count") or 0),
        "follow_up_required_rate": item.get("follow_up_required_rate"),
        "horizon_metrics": _horizon_metrics(item, horizons),
        "analytics_artifact_path": str(analytics_artifact_path),
        "metadata": {},
    }


def _horizon_metrics(item: dict[str, Any], horizons: list[int]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for horizon in horizons:
        metrics[str(horizon)] = {
            "forward_return_mean": item.get(f"forward_{horizon}d_return_mean"),
            "forward_return_median": item.get(f"forward_{horizon}d_return_median"),
            "forward_win_rate": item.get(f"forward_{horizon}d_win_rate"),
            "max_high_return_mean": item.get(f"max_high_return_{horizon}d_mean"),
            "max_low_drawdown_mean": item.get(f"max_low_drawdown_{horizon}d_mean"),
            "max_low_drawdown_worst": item.get(f"max_low_drawdown_{horizon}d_worst"),
        }
    return metrics


def _artifact_paths(json_path: Path) -> tuple[Path, Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_groups.csv"),
        json_path.with_name(f"{json_path.stem}_diagnostics.csv"),
        json_path.with_suffix(".md"),
    )


def _analytics_group_id(*, run_id: str, analytics_level: str, group_value: str) -> str:
    raw = "|".join([run_id, analytics_level, group_value])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_decision_outcome_analytics:{run_id}:{digest}"


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
