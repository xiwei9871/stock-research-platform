"""Auditable PIT finance and valuation backfill planning.

The rolling strategy only reads canonical database tables.  This module is
the maintenance boundary used to plan (and, when explicitly requested,
execute) the missing finance and valuation work identified by a gap workplan.
The pure row builders deliberately keep missing values as ``None``; they
never turn a missing source row into a zero.
"""

from __future__ import annotations

import csv
import inspect
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.loaders.baostock_finance_ingestion import sync_finance_for_assets
from stock_research.consumer_oversold.loaders import load_consumer_finance_history


VALUATION_FACTOR_NAMES = ("pe_ttm", "ps_ttm", "ev_ebitda")
FINANCE_CALC_VERSION = "baostock_v1"
VALUATION_CALC_VERSION = "rolling_oversold_valuation_v1"
WORKPLAN_FINANCE_BUCKET = "finance_backfill"
WORKPLAN_VALUATION_BUCKET = "valuation_backfill"


def load_fundamental_scope(path: str | Path) -> dict[str, list[str]]:
    """Read only eligible finance/valuation IDs from a committed workplan.

    ``gap_rows`` is authoritative when present because it preserves the
    dataset-level reason.  Older bucket-only artifacts remain supported.  BSE
    and invalid-membership IDs are retained in the exclusion report but are
    never returned as adapter candidates.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("fundamental workplan must be a JSON object")
    buckets = payload.get("buckets")
    buckets = buckets if isinstance(buckets, Mapping) else {}
    rows = payload.get("gap_rows")
    rows = rows if isinstance(rows, list) else []

    excluded_bse = _values_from_rows(rows, "out_of_scope_bse")
    excluded_bse.update(_bucket_values(buckets, "out_of_scope_bse"))
    invalid = _values_from_rows(rows, "invalid_membership")
    invalid.update(_bucket_values(buckets, "invalid_membership"))

    finance = _dataset_values(
        rows,
        bucket=WORKPLAN_FINANCE_BUCKET,
        dataset="finance_history",
    )
    valuation = _dataset_values(
        rows,
        bucket=WORKPLAN_VALUATION_BUCKET,
        dataset="valuation_history",
    )
    fallback_finance = set(_bucket_values(buckets, WORKPLAN_FINANCE_BUCKET))
    fallback_valuation = set(_bucket_values(buckets, WORKPLAN_VALUATION_BUCKET))
    if not finance:
        finance = set(fallback_finance)
    if not valuation:
        valuation = set(fallback_valuation)

    # A malformed/legacy workplan can leave a BSE key only in the candidate
    # bucket.  Classify it as out of scope before returning the adapter list.
    for values in (finance, valuation):
        bse = {value for value in values if _is_bse(value)}
        excluded_bse.update(bse)
        values.difference_update(bse)
        values.difference_update(invalid)

    # If a detailed artifact only contained excluded rows, retain the
    # eligible IDs from its bucket-level summary rather than silently
    # returning an empty source request set.
    if not finance and fallback_finance:
        finance = {
            value
            for value in fallback_finance
            if value not in invalid and not _is_bse(value)
        }
    if not valuation and fallback_valuation:
        valuation = {
            value
            for value in fallback_valuation
            if value not in invalid and not _is_bse(value)
        }

    return {
        "finance_assets": sorted(finance),
        "valuation_assets": sorted(valuation),
        "out_of_scope_bse": sorted(excluded_bse),
        "invalid_membership": sorted(invalid),
    }


def build_finance_backfill_rows(
    asset_ids: Sequence[str],
    cutoff: date,
    source_rows: Iterable[Mapping[str, Any]] | pd.DataFrame | None = None,
    *,
    min_report_periods: int = 5,
) -> list[dict[str, Any]]:
    """Return visible PIT finance rows or auditable period requests.

    With source rows, records are normalized and filtered by
    ``announcement_date <= cutoff``.  Without source rows the function emits
    five quarter-period request records (with no financial values), which is
    useful for a dry-run and makes the required TTM history explicit.  A
    request record is not written to ``finance.*``.  When the source returns
    fewer than five periods the shortfall is intentionally preserved; callers
    must report that asset as incomplete rather than fabricating a period.
    """

    cutoff_date = _as_date(cutoff, "cutoff")
    assets = _asset_ids(asset_ids)
    if type(min_report_periods) is not int or min_report_periods < 1:
        raise ValueError("min_report_periods must be a positive integer")
    if not assets:
        return []

    if source_rows is None:
        return [
            {
                "asset_id": asset_id,
                "report_period": report_period,
                "announcement_date": cutoff_date,
                "source": "baostock",
                "calc_version": FINANCE_CALC_VERSION,
                "status": "request",
                "reason": "visible_pit_period_required",
            }
            for asset_id in assets
            for report_period in _quarter_periods(cutoff_date, min_report_periods)
        ]

    normalized: list[dict[str, Any]] = []
    for raw in _records(source_rows):
        asset_id = str(raw.get("asset_id") or "").strip().upper()
        if asset_id not in assets:
            continue
        report_period = _optional_date(raw.get("report_period"), "report_period")
        announcement_date = _optional_date(
            raw.get("announcement_date"), "announcement_date"
        )
        if report_period is None or announcement_date is None:
            continue
        if announcement_date > cutoff_date:
            continue
        row = dict(raw)
        row["asset_id"] = asset_id
        row["report_period"] = report_period
        row["announcement_date"] = announcement_date
        row.setdefault("source", "baostock")
        row.setdefault("calc_version", FINANCE_CALC_VERSION)
        row.setdefault("status", "visible")
        normalized.append(row)

    # Keep the latest source version for a repeated disclosed period while
    # retaining at least one row per period; this is deterministic and avoids
    # accidentally using a later announcement than the cutoff.
    normalized.sort(
        key=lambda row: (
            row["asset_id"],
            row["report_period"],
            row["announcement_date"],
            str(row.get("source") or ""),
            str(row.get("calc_version") or ""),
        ),
        reverse=True,
    )
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, date, date, str, str]] = set()
    for row in normalized:
        key = (
            row["asset_id"],
            row["report_period"],
            row["announcement_date"],
            str(row.get("source") or ""),
            str(row.get("calc_version") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    result.sort(key=lambda row: (row["asset_id"], row["report_period"], row["announcement_date"]))
    return result


def build_valuation_backfill_rows(
    asset_ids: Sequence[str],
    start_date: date,
    end_date: date,
    source_rows: Iterable[Mapping[str, Any]] | pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Return PIT valuation factor rows in the requested window.

    Only the three canonical valuation factors are accepted.  Missing values
    remain ``None`` and are marked as requests, never as zero-valued factors.
    """

    start = _as_date(start_date, "start_date")
    end = _as_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    assets = _asset_ids(asset_ids)
    if not assets:
        return []
    if source_rows is None:
        return [
            {
                "trade_date": end,
                "asset_id": asset_id,
                "factor_name": factor_name,
                "factor_group": "fundamental",
                "factor_value": None,
                "calc_version": VALUATION_CALC_VERSION,
                "source": "factor_daily",
                "source_data_version": "rolling_oversold_fundamentals_v1",
                "status": "request",
                "reason": "valuation_factor_required",
            }
            for asset_id in assets
            for factor_name in VALUATION_FACTOR_NAMES
        ]

    result: list[dict[str, Any]] = []
    for raw in _records(source_rows):
        asset_id = str(raw.get("asset_id") or "").strip().upper()
        factor_name = str(raw.get("factor_name") or "").strip()
        if asset_id not in assets or factor_name not in VALUATION_FACTOR_NAMES:
            continue
        trade_date = _optional_date(raw.get("trade_date"), "trade_date")
        if trade_date is None or not start <= trade_date <= end:
            continue
        computed_at = raw.get("computed_at")
        if computed_at is not None:
            computed_date = _optional_date(computed_at, "computed_at")
            if computed_date is None or computed_date > end:
                continue
        row = dict(raw)
        row["asset_id"] = asset_id
        row["trade_date"] = trade_date
        row["factor_name"] = factor_name
        row.setdefault("factor_group", "fundamental")
        calc_version = str(row.get("calc_version") or "").strip()
        row["calc_version"] = calc_version or VALUATION_CALC_VERSION
        row.setdefault("source", "factor_daily")
        row["source_data_version"] = str(
            row.get("source_data_version") or "rolling_oversold_fundamentals_v1"
        ).strip()
        if computed_at is not None:
            row["computed_at"] = computed_at
        row.setdefault("status", "visible")
        result.append(row)
    result.sort(key=lambda row: (row["asset_id"], row["trade_date"], row["factor_name"]))
    return result


def run_fundamental_backfill(
    *,
    start_date: date | str,
    end_date: date | str,
    gap_workplan: str | Path,
    service: str = SETTINGS.research_service,
    dry_run: bool = True,
    output_dir: str | Path = "outputs/research/rolling_sector_oversold_backfill",
    finance_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan or explicitly execute the finance/valuation backfill.

    The default is dry-run.  Execute mode uses the existing Baostock finance
    adapter for the five requested reporting periods, then writes only source
    valuation rows with non-null values through ``factor_store``.  No request
    record is ever written as a fabricated zero.
    """

    start = _as_date(start_date, "start_date")
    end = _as_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if type(dry_run) is not bool:
        raise TypeError("dry_run must be a boolean")
    scope = load_fundamental_scope(gap_workplan)
    finance_assets = scope["finance_assets"]
    valuation_assets = scope["valuation_assets"]
    finance_rows = build_finance_backfill_rows(finance_assets, end)
    valuation_rows = build_valuation_backfill_rows(valuation_assets, start, end)
    report: dict[str, Any] = {
        "schema_version": "rolling_oversold_fundamental_backfill_v1",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "service": service,
        "dry_run": dry_run,
        "finance": {
            "assets": finance_assets,
            "requested_periods": [
                value.isoformat() for value in _quarter_periods(end, 5)
            ],
            "requested_rows": len(finance_rows),
            "visible_rows": 0,
            "visible_report_periods": {},
            "incomplete_assets": [],
            "written_rows": 0,
            "adapter_results": [],
        },
        "valuation": {
            "assets": valuation_assets,
            "requested_rows": len(valuation_rows),
            "written_rows": 0,
            "incomplete_assets": [],
        },
        "exclusions": {
            "out_of_scope_bse": scope["out_of_scope_bse"],
            "invalid_membership": scope["invalid_membership"],
        },
    }

    if not dry_run:
        adapter = finance_adapter or sync_finance_for_assets
        for report_period in _quarter_periods(end, 5):
            result = _call_finance_adapter(
                adapter,
                asset_ids=finance_assets,
                report_period=report_period,
                cutoff=end,
                service=service,
            )
            report["finance"]["adapter_results"].append(
                {"report_period": report_period.isoformat(), **dict(result or {})}
            )
        source_valuation_rows = _load_valuation_rows(
            valuation_assets, start, end, service=service
        )
        source_finance_rows = _load_finance_rows(
            finance_assets, end, service=service
        )
        visible_finance = build_finance_backfill_rows(
            finance_assets, end, source_rows=source_finance_rows
        )
        report["finance"]["visible_rows"] = len(visible_finance)
        report["finance"]["visible_report_periods"] = {
            asset_id: len(
                {
                    row["report_period"]
                    for row in visible_finance
                    if row["asset_id"] == asset_id
                }
            )
            for asset_id in finance_assets
        }
        report["finance"]["incomplete_assets"] = [
            asset_id
            for asset_id, period_count in report["finance"]["visible_report_periods"].items()
            if period_count < 5
        ]
        visible_valuation = build_valuation_backfill_rows(
            valuation_assets, start, end, source_rows=source_valuation_rows
        )
        writable = [
            row
            for row in visible_valuation
            if _usable_factor_value(row.get("factor_value"))
            and row.get("computed_at") is not None
        ]
        if writable:
            report["valuation"]["written_rows"] = _upsert_valuation_rows(
                writable, service=service
            )
        writable_assets = {row["asset_id"] for row in writable}
        report["valuation"]["incomplete_assets"] = [
            asset_id for asset_id in valuation_assets if asset_id not in writable_assets
        ]
        report["finance"]["written_rows"] = _count_adapter_rows(
            report["finance"]["adapter_results"]
        )

    report["paths"] = _write_report(report, output_dir)
    return report


def _call_finance_adapter(
    adapter: Callable[..., Mapping[str, Any]],
    *,
    asset_ids: list[str],
    report_period: date,
    cutoff: date,
    service: str,
) -> Mapping[str, Any]:
    """Call either a scoped adapter or the legacy period-wide adapter."""

    year = report_period.year
    quarter = (report_period.month - 1) // 3 + 1
    try:
        parameters = inspect.signature(adapter).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "asset_ids" in parameters:
        kwargs: dict[str, Any] = {
            "asset_ids": asset_ids,
            "year": year,
            "quarter": quarter,
            "service": service,
        }
        if "cutoff" in parameters:
            kwargs["cutoff"] = cutoff
        return adapter(**kwargs)
    return adapter(year, quarter, service=service)


def _load_valuation_rows(
    asset_ids: list[str], start: date, end: date, *, service: str
) -> list[dict[str, Any]]:
    if not asset_ids:
        return []
    sql = """
    SELECT trade_date, asset_id, factor_name, factor_group, factor_value,
           calc_version, source, source_data_version, computed_at
    FROM factor.factor_daily
    WHERE asset_id = ANY(%s)
      AND trade_date BETWEEN %s AND %s
      AND factor_name IN ('pe_ttm', 'ps_ttm', 'ev_ebitda')
      AND computed_at < ((%s::date + interval '1 day') AT TIME ZONE 'Asia/Shanghai')
    ORDER BY asset_id, trade_date, factor_name, calc_version
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [asset_ids, start, end, end])


def _upsert_valuation_rows(rows: list[dict[str, Any]], *, service: str) -> int:
    """Upsert only source-backed factors while preserving their PIT timestamp."""

    if not rows:
        return 0
    sql = """
    INSERT INTO factor.factor_daily (
        trade_date, asset_id, factor_name, factor_group, factor_value,
        calc_version, source, source_data_version, computed_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (trade_date, asset_id, factor_name, calc_version)
    DO UPDATE SET
        factor_group = EXCLUDED.factor_group,
        factor_value = EXCLUDED.factor_value,
        source = EXCLUDED.source,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = EXCLUDED.computed_at
    """
    values = [
        (
            row["trade_date"],
            row["asset_id"],
            row["factor_name"],
            row.get("factor_group") or "fundamental",
            row["factor_value"],
            row["calc_version"],
            row.get("source") or "factor_daily",
            row.get("source_data_version") or "rolling_oversold_fundamentals_v1",
            row["computed_at"],
        )
        for row in rows
    ]
    with connect(service) as conn:
        execute_many(conn, sql, values)
    return len(values)


def _load_finance_rows(
    asset_ids: list[str], cutoff: date, *, service: str
) -> list[dict[str, Any]]:
    if not asset_ids:
        return []
    frame = load_consumer_finance_history(
        asset_ids,
        cutoff.isoformat(),
        service=service,
        max_report_periods=5,
    )
    return frame.to_dict("records")


def _write_report(report: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "fundamental_backfill.json"
    csv_path = root / "fundamental_backfill.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    rows: list[dict[str, Any]] = []
    for dataset, section in (("finance_history", report["finance"]), ("valuation_history", report["valuation"])):
        for asset_id in section["assets"]:
            incomplete = asset_id in set(section.get("incomplete_assets", []))
            rows.append(
                {
                    "dataset": dataset,
                    "asset_id": asset_id,
                    "start_date": report["start_date"],
                    "end_date": report["end_date"],
                    "requested_rows": section["requested_rows"],
                    "written_rows": section["written_rows"],
                    "status": (
                        "incomplete"
                        if incomplete
                        else "dry_run"
                        if report["dry_run"]
                        else "executed"
                    ),
                }
            )
    fieldnames = (
        "dataset",
        "asset_id",
        "start_date",
        "end_date",
        "requested_rows",
        "written_rows",
        "status",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {"json": str(json_path), "csv": str(csv_path)}


def _records(rows: Iterable[Mapping[str, Any]] | pd.DataFrame) -> list[dict[str, Any]]:
    if isinstance(rows, pd.DataFrame):
        return rows.to_dict("records")
    if isinstance(rows, (str, bytes)):
        raise TypeError("source_rows must be a row sequence")
    return [dict(row) for row in rows]


def _dataset_values(rows: list[Any], *, bucket: str, dataset: str) -> set[str]:
    return {
        str(row.get("asset_or_key") or "").strip().upper()
        for row in rows
        if isinstance(row, Mapping)
        and row.get("bucket") == bucket
        and row.get("dataset") == dataset
        and str(row.get("asset_or_key") or "").strip()
    }


def _values_from_rows(rows: list[Any], bucket: str) -> set[str]:
    return {
        str(row.get("asset_or_key") or "").strip().upper()
        for row in rows
        if isinstance(row, Mapping)
        and row.get("bucket") == bucket
        and str(row.get("asset_or_key") or "").strip()
    }


def _bucket_values(buckets: Mapping[str, Any], bucket: str) -> list[str]:
    values = buckets.get(bucket, ())
    if isinstance(values, (str, bytes)):
        values = (values,)
    if not isinstance(values, Iterable):
        return []
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def _asset_ids(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError("asset_ids must be a sequence")
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def _is_bse(value: str) -> bool:
    return value.startswith("CN:BJ:")


def _as_date(value: date | str, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _optional_date(value: Any, field: str) -> date | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return _as_date(value, field)
    except ValueError:
        return None


def _usable_factor_value(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _quarter_periods(cutoff: date, count: int) -> list[date]:
    periods: list[date] = []
    year = cutoff.year
    quarter = (cutoff.month - 1) // 3 + 1
    while len(periods) < count:
        month = quarter * 3
        period = date(year, month, 31 if month in {3, 12} else 30)
        if period <= cutoff:
            periods.append(period)
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return periods


def _count_adapter_rows(results: list[Mapping[str, Any]]) -> int:
    total = 0
    for result in results:
        for key in ("indicator_quarter", "income_statement", "share_capital_event"):
            value = result.get(key, 0)
            if isinstance(value, (int, float)):
                total += int(value)
    return total
