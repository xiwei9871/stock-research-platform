"""Read-only classification and serialization for rolling-oversold data gaps."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

from stock_research.strategy_data_policy import DataGap


WORKPLAN_BUCKETS = (
    "invalid_membership",
    "market_bar_backfill",
    "finance_backfill",
    "valuation_backfill",
    "index_backfill",
    "derived_backfill",
    "out_of_scope_bse",
    "out_of_scope_index",
)
DERIVED_DATASETS = {
    "market.industry_daily_bar",
    "market.concept_daily_bar",
}
CSV_COLUMNS = (
    "bucket",
    "dataset",
    "asset_or_key",
    "start_date",
    "end_date",
    "expected_rows",
    "actual_rows",
    "reason",
    "proposed_next_task",
)


class GapAuditRow(TypedDict):
    bucket: str
    dataset: str
    asset_or_key: str
    start_date: str | None
    end_date: str | None
    expected_rows: int
    actual_rows: int
    reason: str
    proposed_next_task: str


class GapWorkplan(TypedDict):
    invalid_membership: list[str]
    market_bar_backfill: list[str]
    finance_backfill: list[str]
    valuation_backfill: list[str]
    index_backfill: list[str]
    derived_backfill: list[str]
    out_of_scope_bse: list[str]
    out_of_scope_index: list[str]
    gap_rows: list[GapAuditRow]


def load_preflight_gaps(path: str | Path) -> tuple[DataGap, ...]:
    """Load DataGap rows from an existing committed preflight artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("gaps")
    if not isinstance(rows, list):
        raise ValueError("preflight gaps must be a list")
    return tuple(DataGap(**row) for row in rows)


def classify_asset_gap(
    *,
    dataset: str,
    asset_id: str,
    asset_master_present: bool,
    list_date: date | None,
    delist_date: date | None,
    cutoff: date,
) -> str:
    """Classify one asset-level gap without accessing or mutating a database."""
    if not asset_master_present:
        return "invalid_membership"
    if asset_id.startswith("CN:BJ:"):
        return "out_of_scope_bse"
    if list_date is not None and list_date > cutoff:
        return "invalid_membership"
    if delist_date is not None and delist_date <= cutoff:
        return "invalid_membership"
    if dataset in {"market_daily_bar", "core.asset_status_daily"}:
        return "market_bar_backfill"
    if dataset == "finance_history":
        return "finance_backfill"
    if dataset == "valuation_history":
        return "valuation_backfill"
    if dataset == "market.index_daily_bar":
        return "index_backfill"
    return "derived_backfill"


def build_gap_workplan(
    *,
    gaps: Iterable[DataGap],
    asset_master: set[str],
    cutoff: date | None = None,
) -> GapWorkplan:
    """Return deterministic buckets plus gap-level audit metadata."""
    effective_cutoff = cutoff or date.max
    master_ids = {str(asset_id).strip() for asset_id in asset_master}
    bucket_values: dict[str, set[str]] = {
        bucket: set() for bucket in WORKPLAN_BUCKETS
    }
    audit_rows: list[dict[str, Any]] = []

    for gap in gaps:
        normalized = _normalize_gap(gap)
        dataset = normalized["dataset"]
        key = normalized["asset_or_key"]

        if dataset == "market.index_daily_bar":
            bucket = (
                "out_of_scope_index" if key == "BSE_50" else "index_backfill"
            )
        elif dataset in DERIVED_DATASETS or normalized["asset_id"] is None:
            bucket = "derived_backfill"
        else:
            bucket = classify_asset_gap(
                dataset=dataset,
                asset_id=key,
                asset_master_present=key in master_ids,
                list_date=None,
                delist_date=None,
                cutoff=effective_cutoff,
            )

        bucket_values[bucket].add(key)
        audit_rows.append(
            {
                "bucket": bucket,
                "dataset": dataset,
                "asset_or_key": key,
                "start_date": normalized["start_date"],
                "end_date": normalized["end_date"],
                "expected_rows": normalized["expected_rows"],
                "actual_rows": normalized["actual_rows"],
                "reason": normalized["reason"],
                "proposed_next_task": _proposed_next_task(bucket, dataset),
            }
        )

    buckets = {
        bucket: sorted(bucket_values[bucket]) for bucket in WORKPLAN_BUCKETS
    }
    audit_rows.sort(
        key=lambda row: (
            row["bucket"],
            row["dataset"],
            row["asset_or_key"],
            row["start_date"] or "",
            row["end_date"] or "",
            row["reason"],
        )
    )
    return {**buckets, "gap_rows": audit_rows}


def write_gap_workplan(
    workplan: Mapping[str, object], output_dir: str | Path
) -> dict[str, str]:
    """Write deterministic JSON and CSV artifacts without database access."""
    buckets = _normalize_workplan_buckets(workplan)
    raw_gap_rows = workplan.get("gap_rows")
    if raw_gap_rows is None:
        legacy_rows = getattr(workplan, "audit_rows", None)
        if legacy_rows is not None:
            raw_gap_rows = legacy_rows
        elif any(buckets.values()):
            raise ValueError("non-empty workplan must include explicit gap_rows")
        else:
            raw_gap_rows = ()
    if isinstance(raw_gap_rows, (str, bytes)) or not isinstance(
        raw_gap_rows, Sequence
    ):
        raise ValueError("workplan gap_rows must be a sequence")
    audit_rows = [_normalize_audit_row(row) for row in raw_gap_rows]
    audit_rows.sort(
        key=lambda row: (
            row["bucket"],
            row["dataset"],
            row["asset_or_key"],
            row["start_date"] or "",
            row["end_date"] or "",
            row["reason"],
        )
    )
    _validate_bucket_audit_alignment(buckets, audit_rows)
    bucket_gap_counts = {
        bucket: sum(row["bucket"] == bucket for row in audit_rows)
        for bucket in WORKPLAN_BUCKETS
    }
    payload = {
        "schema_version": "rolling_oversold_gap_workplan_v1",
        "summary": {
            "total_gap_rows": len(audit_rows),
            "bucket_gap_counts": bucket_gap_counts,
            "bucket_key_counts": {
                bucket: len(values) for bucket, values in buckets.items()
            },
        },
        "buckets": buckets,
        "gap_rows": audit_rows,
    }
    json_content = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(audit_rows)
    csv_content = buffer.getvalue()

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "gap_workplan.json"
    csv_path = root / "gap_workplan.csv"
    json_temp: Path | None = None
    csv_temp: Path | None = None
    try:
        json_temp = _write_temporary(root, ".json.tmp", json_content)
        csv_temp = _write_temporary(root, ".csv.tmp", csv_content)
        os.replace(json_temp, json_path)
        json_temp = None
        os.replace(csv_temp, csv_path)
        csv_temp = None
    finally:
        for temporary in (json_temp, csv_temp):
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"json": str(json_path), "csv": str(csv_path)}


def _gap_value(gap: object, field: str) -> Any:
    if isinstance(gap, Mapping):
        return gap.get(field)
    return getattr(gap, field, None)


def _normalize_gap(gap: object) -> dict[str, Any]:
    dataset = _non_empty_text(_gap_value(gap, "dataset"), "dataset")
    asset_id = _gap_value(gap, "asset_id")
    if asset_id is not None:
        asset_id = _non_empty_text(asset_id, "asset_id")
    sector_system = _optional_text(_gap_value(gap, "sector_system"), "sector_system")
    sector_code = _optional_text(_gap_value(gap, "sector_code"), "sector_code")
    key = asset_id
    if sector_system and sector_code:
        key = key or f"{sector_system}:{sector_code}"
    elif sector_code:
        key = key or sector_code
    if key is None:
        raise ValueError("gap asset/sector key must be non-empty")
    return {
        "dataset": dataset,
        "asset_id": asset_id,
        "asset_or_key": key,
        "start_date": _optional_iso_date(_gap_value(gap, "start_date"), "start_date"),
        "end_date": _optional_iso_date(_gap_value(gap, "end_date"), "end_date"),
        "expected_rows": _non_negative_integer(
            _gap_value(gap, "expected_rows"), "expected_rows"
        ),
        "actual_rows": _non_negative_integer(
            _gap_value(gap, "actual_rows"), "actual_rows"
        ),
        "reason": _non_empty_text(_gap_value(gap, "reason"), "reason"),
    }


def _normalize_audit_row(row: object) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("workplan gap_rows entries must be mappings")
    bucket = _non_empty_text(row.get("bucket"), "bucket")
    if bucket not in WORKPLAN_BUCKETS:
        raise ValueError(f"workplan gap_rows bucket must be one of {WORKPLAN_BUCKETS}")
    return {
        "bucket": bucket,
        "dataset": _non_empty_text(row.get("dataset"), "dataset"),
        "asset_or_key": _non_empty_text(
            row.get("asset_or_key"), "asset/sector key"
        ),
        "start_date": _optional_iso_date(row.get("start_date"), "start_date"),
        "end_date": _optional_iso_date(row.get("end_date"), "end_date"),
        "expected_rows": _non_negative_integer(
            row.get("expected_rows"), "expected_rows"
        ),
        "actual_rows": _non_negative_integer(row.get("actual_rows"), "actual_rows"),
        "reason": _non_empty_text(row.get("reason"), "reason"),
        "proposed_next_task": _non_empty_text(
            row.get("proposed_next_task"), "proposed_next_task"
        ),
    }


def _normalize_workplan_buckets(
    workplan: Mapping[str, object],
) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for bucket in WORKPLAN_BUCKETS:
        values = workplan.get(bucket, ())
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValueError(f"workplan bucket {bucket} must be a sequence")
        buckets[bucket] = sorted(
            {_non_empty_text(value, f"workplan bucket {bucket} key") for value in values}
        )
    return buckets


def _validate_bucket_audit_alignment(
    buckets: Mapping[str, Sequence[str]], audit_rows: Sequence[Mapping[str, Any]]
) -> None:
    audited = {bucket: set() for bucket in WORKPLAN_BUCKETS}
    for row in audit_rows:
        audited[str(row["bucket"])].add(str(row["asset_or_key"]))
    for bucket in WORKPLAN_BUCKETS:
        if set(buckets[bucket]) != audited[bucket]:
            raise ValueError(
                f"workplan bucket {bucket} keys must match explicit gap_rows"
            )


def _non_empty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"gap {field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _non_empty_text(value, field)


def _optional_iso_date(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"gap {field} must use YYYY-MM-DD or be null")
    try:
        normalized = date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"gap {field} must use YYYY-MM-DD or be null") from exc
    if normalized != value:
        raise ValueError(f"gap {field} must use YYYY-MM-DD or be null")
    return value


def _non_negative_integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"gap {field} must be a non-negative integer")
    return value


def _write_temporary(root: Path, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=root,
        prefix=".gap_workplan.",
        suffix=suffix,
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _proposed_next_task(bucket: str, dataset: str) -> str:
    if bucket == "invalid_membership":
        return "repair_membership_or_asset_code"
    if bucket in {"out_of_scope_bse", "out_of_scope_index"}:
        return "no_backfill_out_of_scope"
    if dataset == "market_daily_bar":
        return "backfill_market_daily_bar"
    if dataset == "core.asset_status_daily":
        return "rebuild_asset_status_daily"
    if bucket == "finance_backfill":
        return "backfill_finance_history"
    if bucket == "valuation_backfill":
        return "backfill_valuation_history"
    if bucket == "index_backfill":
        return "backfill_index_daily_bar"
    return "rebuild_derived_daily_bar"
