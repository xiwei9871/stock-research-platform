from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


@dataclass(frozen=True)
class OperatorDataset:
    name: str
    filename_stem: str
    columns: list[str]
    query_factory: Callable[[dict[str, Any]], tuple[str, list[Any]]]


def export_operator_review(
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    *,
    status: str | None = None,
    section_group: str | None = None,
    portfolio_id: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be <= end_date")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "section_group": section_group,
        "portfolio_id": portfolio_id,
    }
    row_counts: dict[str, int] = {}
    files: dict[str, str] = {}
    json_files: dict[str, str] = {}

    with connect(service) as conn:
        for dataset in OPERATOR_DATASETS:
            sql, params = dataset.query_factory(filters)
            rows = fetch_all(conn, sql, params)
            frame = pd.DataFrame(rows).reindex(columns=dataset.columns)
            csv_path = output_path / f"{dataset.filename_stem}.csv"
            json_path = output_path / f"{dataset.filename_stem}.json"
            frame.to_csv(csv_path, index=False)
            json_path.write_text(
                json.dumps(
                    [_json_safe_record(row) for row in frame.to_dict("records")],
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
                encoding="utf-8",
            )
            row_counts[dataset.name] = int(len(frame))
            files[dataset.name] = str(csv_path)
            json_files[dataset.name] = str(json_path)

    manifest = {
        "filters": filters,
        "row_counts": row_counts,
        "files": files,
        "json_files": json_files,
    }
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return {**manifest, "manifest_path": str(manifest_path)}


def _review_runs_query(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where = ["r.trade_date BETWEEN %s AND %s"]
    params: list[Any] = [filters["start_date"], filters["end_date"]]
    if filters.get("status"):
        where.append("r.status = %s")
        params.append(filters["status"])
    sql = f"""
        SELECT r.trade_date, r.run_id, r.status AS run_status,
               r.blocker_count, r.warning_count, r.json_path, r.markdown_path
        FROM ops.p2_review_run r
        WHERE {" AND ".join(where)}
        ORDER BY r.trade_date DESC, r.run_id
    """
    return sql, params


def _review_sections_query(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where = ["r.trade_date BETWEEN %s AND %s"]
    params: list[Any] = [filters["start_date"], filters["end_date"]]
    if filters.get("status"):
        where.append("r.status = %s")
        params.append(filters["status"])
    if filters.get("section_group"):
        where.append("s.section_group = %s")
        params.append(filters["section_group"])
    sql = f"""
        SELECT r.trade_date, s.run_id, s.section_group, s.section_name,
               s.status AS section_status, s.required, s.exists,
               s.source_artifact_path
        FROM ops.p2_review_section s
        JOIN ops.p2_review_run r ON r.run_id = s.run_id
        WHERE {" AND ".join(where)}
        ORDER BY r.trade_date DESC, s.section_group, s.section_name
    """
    return sql, params


def _portfolio_risk_query(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where = ["v.trade_date BETWEEN %s AND %s"]
    params: list[Any] = [filters["start_date"], filters["end_date"]]
    if filters.get("status"):
        where.append("v.review_status = %s")
        params.append(filters["status"])
    if filters.get("portfolio_id"):
        where.append("v.portfolio_id = %s")
        params.append(filters["portfolio_id"])
    sql = f"""
        SELECT v.trade_date, v.portfolio_id, v.strategy_id,
               v.review_status, v.risk_level, v.drawdown, v.exposure_pct,
               v.open_position_count, v.source_artifact_path
        FROM simulation.virtual_portfolio_state_daily v
        WHERE {" AND ".join(where)}
        ORDER BY v.trade_date DESC, v.portfolio_id, v.strategy_id
    """
    return sql, params


def _latest_status_query(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where = ["r.trade_date BETWEEN %s AND %s"]
    params: list[Any] = [filters["start_date"], filters["end_date"]]
    if filters.get("status"):
        where.append("r.status = %s")
        params.append(filters["status"])
    sql = f"""
        SELECT DISTINCT ON (r.trade_date)
               r.trade_date, r.run_id, r.status AS run_status,
               r.blocker_count, r.warning_count, r.json_path, r.markdown_path
        FROM ops.p2_review_run r
        WHERE {" AND ".join(where)}
        ORDER BY r.trade_date DESC, r.updated_at DESC, r.run_id
    """
    return sql, params


def _json_safe_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in row.items()}


def _json_safe_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


OPERATOR_DATASETS = [
    OperatorDataset(
        name="review_runs",
        filename_stem="review_runs",
        columns=[
            "trade_date",
            "run_id",
            "run_status",
            "blocker_count",
            "warning_count",
            "json_path",
            "markdown_path",
        ],
        query_factory=_review_runs_query,
    ),
    OperatorDataset(
        name="review_sections",
        filename_stem="review_sections",
        columns=[
            "trade_date",
            "run_id",
            "section_group",
            "section_name",
            "section_status",
            "required",
            "exists",
            "source_artifact_path",
        ],
        query_factory=_review_sections_query,
    ),
    OperatorDataset(
        name="portfolio_risk",
        filename_stem="portfolio_risk",
        columns=[
            "trade_date",
            "portfolio_id",
            "strategy_id",
            "review_status",
            "risk_level",
            "drawdown",
            "exposure_pct",
            "open_position_count",
            "source_artifact_path",
        ],
        query_factory=_portfolio_risk_query,
    ),
    OperatorDataset(
        name="latest_status_by_trade_date",
        filename_stem="latest_status_by_trade_date",
        columns=[
            "trade_date",
            "run_id",
            "run_status",
            "blocker_count",
            "warning_count",
            "json_path",
            "markdown_path",
        ],
        query_factory=_latest_status_query,
    ),
]
