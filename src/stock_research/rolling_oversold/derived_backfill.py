"""Database-only rebuilds for rolling oversold derived datasets.

The rolling strategy reads these tables only after this maintenance job has
rebuilt them.  Source adapters are kept behind the explicit index-sync call;
the strategy pipeline does not import this module.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.core_data import (
    build_asset_status_daily_for_service,
    build_concept_daily_bars_for_service,
    build_industry_daily_bars_for_service,
)
from stock_research.db import connect, fetch_all
from stock_research.loaders.baostock_ingestion import sync_index_daily_bars


SUPPORTED_INDEX_IDS = ("STAR_50",)
OUT_OF_SCOPE_INDEX_IDS = ("BSE_50",)
DEFAULT_INDEX_IDS = ("STAR_50",)
MIN_INDEX_SESSIONS = 252
DEFAULT_OUTPUT_DIR = Path("outputs/research/rolling_sector_oversold_derived_backfill")
LEGACY_INDUSTRY_SYSTEMS = frozenset({"csrc", "sw", "citics", "citic", "swhy"})


def load_derived_scope(path: str | Path) -> dict[str, list[str]]:
    """Read derived/index systems from a gap workplan.

    A workplan with detailed ``gap_rows`` is preferred.  Older artifacts only
    contain buckets, so those remain supported as a fallback.  BSE_50 is kept
    as an audit-only exclusion and is never returned in ``index_ids``.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("gap_rows", [])
    detailed = rows if isinstance(rows, list) and rows else []

    industry_values = _keys_from_rows(
        detailed,
        bucket="derived_backfill",
        dataset="market.industry_daily_bar",
    )
    concept_values = _keys_from_rows(
        detailed,
        bucket="derived_backfill",
        dataset="market.concept_daily_bar",
    )
    index_values = _keys_from_rows(
        detailed,
        bucket="index_backfill",
        dataset="market.index_daily_bar",
    )
    excluded_values = _keys_from_rows(
        detailed,
        bucket="out_of_scope_index",
        dataset="market.index_daily_bar",
    )

    buckets = payload.get("buckets", {})
    if not industry_values or not concept_values:
        bucket_industry, bucket_concept = _split_legacy_derived_values(
            buckets.get("derived_backfill", ())
        )
        if not industry_values:
            industry_values = bucket_industry
        if not concept_values:
            concept_values = bucket_concept
    if not index_values:
        index_values = _clean_values(buckets.get("index_backfill", ()))
    if not excluded_values:
        excluded_values = _clean_values(buckets.get("out_of_scope_index", ()))

    index_ids = sorted(
        value for value in set(index_values) if value not in OUT_OF_SCOPE_INDEX_IDS
    )
    excluded = sorted(
        set(excluded_values)
        | {value for value in index_values if value in OUT_OF_SCOPE_INDEX_IDS}
    )
    return {
        "industry_systems": _systems_from_keys(industry_values),
        "concept_systems": _systems_from_keys(concept_values),
        "index_ids": index_ids,
        "out_of_scope_index": excluded,
    }


def run_derived_backfill(
    *,
    start_date: str | date,
    end_date: str | date,
    industry_systems: Sequence[str] | None = None,
    concept_systems: Sequence[str] | None = None,
    index_ids: Sequence[str] | None = None,
    gap_workplan: str | Path | None = None,
    service: str = SETTINGS.research_service,
    dry_run: bool = True,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Rebuild status, sector bars, and in-scope index bars for a window."""
    parsed_start = _parse_date(start_date, "start_date")
    parsed_end = _parse_date(end_date, "end_date")
    if parsed_end < parsed_start:
        raise ValueError("end_date must not precede start_date")

    if gap_workplan:
        scope = load_derived_scope(gap_workplan)
    elif industry_systems is None and concept_systems is None and index_ids is None:
        scope = discover_derived_scope(
            service=service,
            start_date=parsed_start.isoformat(),
            end_date=parsed_end.isoformat(),
        )
    else:
        scope = {}
    resolved_industry = _normalize_systems(
        industry_systems if industry_systems is not None else scope.get("industry_systems", ())
    )
    resolved_concept = _normalize_systems(
        concept_systems if concept_systems is not None else scope.get("concept_systems", ())
    )
    requested_indices = _normalize_systems(
        index_ids if index_ids is not None else scope.get("index_ids", DEFAULT_INDEX_IDS)
    )
    workplan_excluded = _normalize_systems(scope.get("out_of_scope_index", ()))
    eligible_indices: list[str] = []
    excluded_indices = set(workplan_excluded)
    for index_id in requested_indices:
        if index_id in OUT_OF_SCOPE_INDEX_IDS:
            excluded_indices.add(index_id)
        elif index_id in SUPPORTED_INDEX_IDS:
            eligible_indices.append(index_id)
        else:
            raise ValueError(f"unsupported rolling oversold index: {index_id}")
    eligible_indices = sorted(set(eligible_indices))
    excluded_indices.update(
        index_id for index_id in excluded_indices if index_id in OUT_OF_SCOPE_INDEX_IDS
    )

    start_text = parsed_start.isoformat()
    end_text = parsed_end.isoformat()
    status_state: dict[str, Any] = {
        "status": "planned" if dry_run else "executed",
        "start_date": start_text,
        "end_date": end_text,
        "adjust_type": "hfq",
    }
    industry_state: dict[str, Any] = {
        "status": "planned" if dry_run else "executed",
        "start_date": start_text,
        "end_date": end_text,
        "adjust_type": "qfq",
        "systems": resolved_industry,
    }
    concept_state: dict[str, Any] = {
        "status": "planned" if dry_run else "executed",
        "start_date": start_text,
        "end_date": end_text,
        "adjust_type": "qfq",
        "systems": resolved_concept,
    }
    index_state: dict[str, Any] = {
        "status": "planned" if dry_run else "executed",
        "start_date": start_text,
        "end_date": end_text,
        "indices": eligible_indices,
        "coverage": {},
    }

    if not dry_run:
        build_asset_status_daily_for_service(
            start_date=start_text,
            end_date=end_text,
            adjust_type="hfq",
            service=service,
        )
        for system in resolved_industry:
            build_industry_daily_bars_for_service(
                start_date=start_text,
                end_date=end_text,
                industry_system=system,
                adjust_type="qfq",
                service=service,
            )
        for system in resolved_concept:
            build_concept_daily_bars_for_service(
                start_date=start_text,
                end_date=end_text,
                concept_system=system,
                adjust_type="qfq",
                service=service,
            )
        if eligible_indices:
            index_state["rows_written"] = int(
                sync_index_daily_bars(
                    start_date=start_text,
                    end_date=end_text,
                    service=service,
                    index_ids=tuple(eligible_indices),
                )
                or 0
            )
            index_state["coverage"] = verify_index_coverage(
                service=service,
                start_date=start_text,
                end_date=end_text,
                index_ids=tuple(eligible_indices),
            )

    report = {
        "schema_version": "rolling_oversold_derived_backfill_v1",
        "start_date": start_text,
        "end_date": end_text,
        "service": service,
        "dry_run": dry_run,
        "asset_status_daily": status_state,
        "industry_daily_bar": industry_state,
        "concept_daily_bar": concept_state,
        "index_daily_bar": index_state,
        "out_of_scope_index": sorted(excluded_indices),
    }
    paths = _write_report(report, output_dir)
    report["paths"] = paths
    return report


def discover_derived_scope(
    *,
    service: str,
    start_date: str,
    end_date: str,
) -> dict[str, list[str]]:
    """Discover active membership systems from the database when no workplan is given."""
    sql = """
    SELECT 'industry' AS scope_kind, industry_system AS system
    FROM core.industry_membership
    WHERE start_date <= %s
      AND (end_date IS NULL OR end_date > %s)
    UNION
    SELECT 'concept' AS scope_kind, concept_system AS system
    FROM core.concept_membership
    WHERE start_date <= %s
      AND (end_date IS NULL OR end_date > %s)
    ORDER BY scope_kind, system
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [end_date, start_date, end_date, start_date])
    industry = sorted(
        {
            str(row.get("system") or "").strip()
            for row in rows
            if row.get("scope_kind") == "industry" and str(row.get("system") or "").strip()
        }
    )
    concept = sorted(
        {
            str(row.get("system") or "").strip()
            for row in rows
            if row.get("scope_kind") == "concept" and str(row.get("system") or "").strip()
        }
    )
    return {
        "industry_systems": industry,
        "concept_systems": concept,
        "index_ids": list(DEFAULT_INDEX_IDS),
        "out_of_scope_index": list(OUT_OF_SCOPE_INDEX_IDS),
    }


def verify_index_coverage(
    *,
    service: str,
    start_date: str,
    end_date: str,
    index_ids: Sequence[str],
    minimum_sessions: int = MIN_INDEX_SESSIONS,
) -> dict[str, int]:
    """Verify non-null close coverage after an index sync."""
    selected = sorted(set(index_ids))
    if not selected:
        return {}
    sql = """
    SELECT index_id, count(*)::int AS non_null_close_rows
    FROM market.index_daily_bar
    WHERE index_id = ANY(%s)
      AND trade_date >= %s
      AND trade_date <= %s
      AND close IS NOT NULL
    GROUP BY index_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [selected, start_date, end_date])
    coverage = {str(row["index_id"]): int(row.get("non_null_close_rows") or 0) for row in rows}
    missing = {
        index_id: coverage.get(index_id, 0)
        for index_id in selected
        if coverage.get(index_id, 0) < minimum_sessions
    }
    if missing:
        details = ", ".join(f"{key}={value}" for key, value in sorted(missing.items()))
        raise RuntimeError(
            f"rolling oversold index coverage below {minimum_sessions} sessions: {details}"
        )
    return coverage


def _keys_from_rows(rows: Iterable[dict[str, Any]], *, bucket: str, dataset: str) -> list[str]:
    return _clean_values(
        row.get("asset_or_key")
        for row in rows
        if row.get("bucket") == bucket and row.get("dataset") == dataset
    )


def _split_legacy_derived_values(values: Iterable[Any]) -> tuple[list[str], list[str]]:
    industry: list[str] = []
    concept: list[str] = []
    for value in _clean_values(values):
        system = value.split(":", 1)[0]
        if system in LEGACY_INDUSTRY_SYSTEMS:
            industry.append(value)
        else:
            concept.append(value)
    return industry, concept


def _systems_from_keys(values: Iterable[str]) -> list[str]:
    return sorted({value.split(":", 1)[0] for value in values if ":" in value})


def _clean_values(values: Iterable[Any]) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        values = (values,)
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _normalize_systems(values: Sequence[str] | Iterable[str]) -> list[str]:
    return _clean_values(values)


def _parse_date(value: str | date, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _write_report(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "derived_backfill_report.json"
    csv_path = root / "derived_backfill_report.csv"
    paths = {"json": str(json_path), "csv": str(csv_path)}
    report["paths"] = paths
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        {
            "dataset": "asset_status_daily",
            "status": report["asset_status_daily"]["status"],
            "systems": "",
            "indices": "",
        },
        {
            "dataset": "industry_daily_bar",
            "status": report["industry_daily_bar"]["status"],
            "systems": ",".join(report["industry_daily_bar"]["systems"]),
            "indices": "",
        },
        {
            "dataset": "concept_daily_bar",
            "status": report["concept_daily_bar"]["status"],
            "systems": ",".join(report["concept_daily_bar"]["systems"]),
            "indices": "",
        },
        {
            "dataset": "index_daily_bar",
            "status": report["index_daily_bar"]["status"],
            "systems": "",
            "indices": ",".join(report["index_daily_bar"]["indices"]),
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("dataset", "status", "systems", "indices"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return paths
