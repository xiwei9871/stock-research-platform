"""Read-only classification and serialization for rolling-oversold data gaps."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

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


class GapWorkplan(dict[str, list[str]]):
    """Bucket mapping with the original gap-level audit rows attached."""

    def __init__(
        self,
        buckets: Mapping[str, Sequence[str]],
        *,
        audit_rows: Iterable[Mapping[str, Any]],
    ) -> None:
        super().__init__(
            (bucket, list(buckets.get(bucket, ()))) for bucket in WORKPLAN_BUCKETS
        )
        self.audit_rows = tuple(dict(row) for row in audit_rows)


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
        dataset = str(_gap_value(gap, "dataset") or "").strip()
        if not dataset:
            raise ValueError("gap dataset must be non-empty")
        key = _gap_key(gap, dataset)

        if dataset == "market.index_daily_bar":
            bucket = (
                "out_of_scope_index" if key == "BSE_50" else "index_backfill"
            )
        elif dataset in DERIVED_DATASETS or _gap_value(gap, "asset_id") is None:
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
                "start_date": _gap_value(gap, "start_date"),
                "end_date": _gap_value(gap, "end_date"),
                "expected_rows": int(_gap_value(gap, "expected_rows") or 0),
                "actual_rows": int(_gap_value(gap, "actual_rows") or 0),
                "reason": str(_gap_value(gap, "reason") or ""),
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
    return GapWorkplan(buckets, audit_rows=audit_rows)


def write_gap_workplan(
    workplan: dict[str, list[str]], output_dir: str | Path
) -> dict[str, str]:
    """Write deterministic JSON and CSV artifacts without database access."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "gap_workplan.json"
    csv_path = root / "gap_workplan.csv"

    buckets = {
        bucket: sorted(set(workplan.get(bucket, ()))) for bucket in WORKPLAN_BUCKETS
    }
    audit_rows = [dict(row) for row in getattr(workplan, "audit_rows", ())]
    if not audit_rows:
        raise ValueError("workplan must retain gap-level audit rows")
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
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(audit_rows)
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path)}


def _gap_value(gap: object, field: str) -> Any:
    if isinstance(gap, Mapping):
        return gap.get(field)
    return getattr(gap, field, None)


def _gap_key(gap: object, dataset: str) -> str:
    asset_id = _gap_value(gap, "asset_id")
    if asset_id is not None and str(asset_id).strip():
        return str(asset_id).strip()
    sector_system = str(_gap_value(gap, "sector_system") or "").strip()
    sector_code = str(_gap_value(gap, "sector_code") or "").strip()
    if sector_system and sector_code:
        return f"{sector_system}:{sector_code}"
    if sector_code:
        return sector_code
    return dataset


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
