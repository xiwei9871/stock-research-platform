"""Read-only classification and serialization for rolling-oversold data gaps."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd

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


def audit_target_asset_coverage(
    *,
    asset_ids: Iterable[object],
    market_rows: pd.DataFrame,
    status_rows: pd.DataFrame,
    finance_rows: pd.DataFrame,
    valuation_rows: pd.DataFrame,
    start_date: date,
    end_date: date,
    expected_trade_dates: Iterable[date] | None = None,
) -> dict[str, object]:
    """Audit the required database coverage for a PIT target asset union.

    ``asset_ids`` is expected to be the already-filtered active, master-present
    non-BSE union produced by the membership backfill.  The helper remains
    read-only and deliberately accepts frames so callers can freeze the
    database extracts and serialize an auditable result without any source
    fallback.

    Market coverage is checked on the supplied expected trading dates (or the
    observed union when no explicit calendar is supplied) where a matching
    status row says the asset was tradable, non-ST, and not suspended.  Status
    coverage is required wherever a qfq market date is observed and for the
    latest cutoff date; sparse lifecycle/non-trading dates without a market
    bar are not treated as download tasks.  This prevents a suspended stock's
    null activity from becoming a false market-download task while still
    surfacing an absent cutoff row.
    """

    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise TypeError("start_date and end_date must be date values")
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    eligible_assets, excluded_bse_assets = _normalize_target_asset_ids(asset_ids)
    expected_dates = _normalize_expected_trade_dates(
        expected_trade_dates,
        market_rows=market_rows,
        status_rows=status_rows,
        start_date=start_date,
        end_date=end_date,
    )

    market = _coverage_frame(market_rows, start_date=start_date, end_date=end_date)
    status = _coverage_frame(status_rows, start_date=start_date, end_date=end_date)
    market = _select_qfq_rows(market)

    market_presence_keys = {
        (str(row.asset_id), row.trade_date.date())
        for row in market.itertuples(index=False)
    }
    market_dates_by_asset: dict[str, set[date]] = {}
    for asset_id, trade_date in market_presence_keys:
        market_dates_by_asset.setdefault(asset_id, set()).add(trade_date)
    market_keys = {
        (str(row.asset_id), row.trade_date.date())
        for row in market.itertuples(index=False)
        if _positive_number(getattr(row, "close", None)) is not None
    }
    market_activity_keys = {
        (str(row.asset_id), row.trade_date.date())
        for row in market.itertuples(index=False)
        if _positive_number(getattr(row, "close", None)) is not None
        and _non_negative_number(getattr(row, "amount", None)) is not None
    }
    status_by_asset_date: dict[tuple[str, date], dict[str, object]] = {}
    for row in status.to_dict(orient="records"):
        asset_id = str(row.get("asset_id") or "").strip()
        trade_date = row.get("trade_date")
        if asset_id and isinstance(trade_date, pd.Timestamp):
            status_by_asset_date[(asset_id, trade_date.date())] = row

    status_missing_rows: list[dict[str, object]] = []
    market_missing_rows: list[dict[str, object]] = []
    market_activity_missing_rows: list[dict[str, object]] = []
    for asset_id in eligible_assets:
        observed_dates = {
            trade_date
            for (status_asset, trade_date) in status_by_asset_date
            if status_asset == asset_id
        }
        observed_dates.update(market_dates_by_asset.get(asset_id, set()))
        for trade_date in sorted(set(expected_dates).union(observed_dates)):
            status_row = status_by_asset_date.get((asset_id, trade_date))
            if status_row is None:
                # Status history is sparse on lifecycle/non-trading dates.  A
                # missing row is actionable when a qfq bar exists for that
                # date, or when the date is the required latest cutoff row.
                if (
                    trade_date in market_dates_by_asset.get(asset_id, set())
                    or trade_date == end_date
                ):
                    status_missing_rows.append(
                        {"asset_id": asset_id, "trade_date": trade_date.isoformat()}
                    )
                continue
            if not _status_is_tradable(status_row):
                continue
            key = (asset_id, trade_date)
            if key not in market_keys:
                market_missing_rows.append(
                    {"asset_id": asset_id, "trade_date": trade_date.isoformat()}
                )
            elif key not in market_activity_keys:
                market_activity_missing_rows.append(
                    {"asset_id": asset_id, "trade_date": trade_date.isoformat()}
                )
    finance_missing_assets = _missing_finance_assets(
        eligible_assets, finance_rows, end_date=end_date
    )
    valuation_missing_assets = _missing_valuation_assets(
        eligible_assets, valuation_rows, end_date=end_date
    )
    market_missing_assets = sorted(
        {str(row["asset_id"]) for row in market_missing_rows}
    )
    market_activity_missing_assets = sorted(
        {str(row["asset_id"]) for row in market_activity_missing_rows}
    )
    status_missing_assets = sorted(
        {str(row["asset_id"]) for row in status_missing_rows}
    )
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "expected_trade_dates": [trade_date.isoformat() for trade_date in expected_dates],
        "eligible_asset_ids": eligible_assets,
        "excluded_bse_assets": excluded_bse_assets,
        "market_missing_assets": market_missing_assets,
        "market_missing_rows": market_missing_rows,
        "market_activity_missing_assets": market_activity_missing_assets,
        "market_activity_missing_rows": market_activity_missing_rows,
        "status_missing_assets": status_missing_assets,
        "status_missing_rows": status_missing_rows,
        "finance_missing_assets": finance_missing_assets,
        "valuation_missing_assets": valuation_missing_assets,
        "summary": {
            "eligible_assets": len(eligible_assets),
            "excluded_bse_assets": len(excluded_bse_assets),
            "expected_trade_dates": len(expected_dates),
            "market_missing_assets": len(market_missing_assets),
            "market_activity_missing_assets": len(market_activity_missing_assets),
            "status_missing_assets": len(status_missing_assets),
            "finance_missing_assets": len(finance_missing_assets),
            "valuation_missing_assets": len(valuation_missing_assets),
        },
    }


def _normalize_target_asset_ids(
    asset_ids: Iterable[object],
) -> tuple[list[str], list[str]]:
    normalized = {str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()}
    excluded = sorted(asset_id for asset_id in normalized if asset_id.startswith("CN:BJ:"))
    eligible = sorted(normalized - set(excluded))
    return eligible, excluded


def _coverage_frame(
    frame: object,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["asset_id", "trade_date"])
    if not {"asset_id", "trade_date"}.issubset(frame.columns):
        return pd.DataFrame(columns=["asset_id", "trade_date"])
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result.loc[
        result["asset_id"].notna()
        & result["trade_date"].notna()
        & result["trade_date"].ge(pd.Timestamp(start_date))
        & result["trade_date"].le(pd.Timestamp(end_date))
    ].copy()
    return result.drop_duplicates(["asset_id", "trade_date"], keep="last")


def _select_qfq_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "adjust_type" not in frame.columns:
        return frame
    return frame.loc[frame["adjust_type"].astype("string").str.casefold().eq("qfq")].copy()


def _normalize_expected_trade_dates(
    expected_trade_dates: Iterable[date] | None,
    *,
    market_rows: object,
    status_rows: object,
    start_date: date,
    end_date: date,
) -> list[date]:
    if expected_trade_dates is not None:
        dates = {
            value
            for value in (_coerce_date(item) for item in expected_trade_dates)
            if value is not None and start_date <= value <= end_date
        }
        dates.update((start_date, end_date))
        return sorted(dates)
    return _coverage_window_dates(
        market_rows=market_rows,
        status_rows=status_rows,
        start_date=start_date,
        end_date=end_date,
    )


def _coverage_window_dates(
    *,
    market_rows: object,
    status_rows: object,
    start_date: date,
    end_date: date,
) -> list[date]:
    dates: set[date] = {start_date, end_date}
    for frame in (market_rows, status_rows):
        if not isinstance(frame, pd.DataFrame) or "trade_date" not in frame.columns:
            continue
        values = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
        dates.update(
            value.date()
            for value in values
            if start_date <= value.date() <= end_date
        )
    return sorted(dates)


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _status_is_tradable(row: Mapping[str, object]) -> bool:
    if "is_trade" in row and not _status_flag(row.get("is_trade")):
        return False
    if _status_flag(row.get("is_st")):
        return False
    if _status_flag(row.get("is_suspended")):
        return False
    return True


def _status_flag(value: object) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _non_negative_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _missing_finance_assets(
    asset_ids: Sequence[str], frame: object, *, end_date: date
) -> list[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "asset_id" not in frame.columns:
        return list(asset_ids)
    normalized = frame.copy(deep=True)
    normalized["asset_id"] = normalized["asset_id"].astype("string").str.strip()
    date_column = _first_date_column(normalized, ("announcement_date",))
    if date_column is None:
        return list(asset_ids)
    normalized[date_column] = pd.to_datetime(normalized[date_column], errors="coerce")
    normalized = normalized.loc[
        normalized[date_column].notna()
        & normalized[date_column].le(pd.Timestamp(end_date))
    ]
    supported: set[str] = set()
    for row in normalized.to_dict(orient="records"):
        asset_id = str(row.get("asset_id") or "").strip()
        if not asset_id:
            continue
        if _finite_number(row.get("roe")) is not None and _positive_number(row.get("total_share")) is not None:
            supported.add(asset_id)
    return sorted(set(asset_ids) - supported)


def _missing_valuation_assets(
    asset_ids: Sequence[str], frame: object, *, end_date: date
) -> list[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "asset_id" not in frame.columns:
        return list(asset_ids)
    normalized = frame.copy(deep=True)
    normalized["asset_id"] = normalized["asset_id"].astype("string").str.strip()
    date_column = _first_date_column(normalized, ("valuation_date", "trade_date"))
    if date_column is None:
        return list(asset_ids)
    normalized[date_column] = pd.to_datetime(normalized[date_column], errors="coerce")
    normalized = normalized.loc[
        normalized[date_column].notna()
        & normalized[date_column].le(pd.Timestamp(end_date))
    ]
    supported: set[str] = set()
    if "factor_name" in normalized.columns and "factor_value" in normalized.columns:
        for row in normalized.to_dict(orient="records"):
            if str(row.get("factor_name") or "").strip() not in {"pe_ttm", "ps_ttm"}:
                continue
            if _positive_number(row.get("factor_value")) is not None:
                supported.add(str(row.get("asset_id") or "").strip())
    else:
        for row in normalized.to_dict(orient="records"):
            asset_id = str(row.get("asset_id") or "").strip()
            if not asset_id:
                continue
            if _positive_number(row.get("pe_ttm")) is not None or _positive_number(row.get("ps_ttm")) is not None:
                supported.add(asset_id)
    return sorted(set(asset_ids) - supported)


def _first_date_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    return next((name for name in candidates if name in frame.columns), None)


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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
    audit_rows.sort(key=_audit_row_sort_key)
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
    audit_rows.sort(key=_audit_row_sort_key)
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
    previous_targets = {
        json_path: _read_existing_text(json_path),
        csv_path: _read_existing_text(csv_path),
    }
    json_temp: Path | None = None
    csv_temp: Path | None = None
    try:
        json_temp = _write_temporary(root, ".json.tmp", json_content)
        csv_temp = _write_temporary(root, ".csv.tmp", csv_content)
        os.replace(json_temp, json_path)
        json_temp = None
        os.replace(csv_temp, csv_path)
        csv_temp = None
    except BaseException:
        _restore_target(json_path, previous_targets[json_path])
        _restore_target(csv_path, previous_targets[csv_path])
        raise
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


def _audit_row_sort_key(row: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        row["bucket"],
        row["dataset"],
        row["asset_or_key"],
        row["start_date"] or "",
        row["end_date"] or "",
        row["expected_rows"],
        row["actual_rows"],
        row["reason"],
        row["proposed_next_task"],
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
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=root,
            prefix=".gap_workplan.",
            suffix=suffix,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _read_existing_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _restore_target(path: Path, previous: str | None) -> None:
    current = _read_existing_text(path)
    if current == previous:
        return
    if previous is None:
        path.unlink(missing_ok=True)
        return

    temporary = _write_temporary(path.parent, ".restore.tmp", previous)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
