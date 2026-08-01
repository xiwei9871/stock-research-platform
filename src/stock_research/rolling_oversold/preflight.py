"""Fail-closed coverage checks for rolling oversold database inputs."""

from __future__ import annotations

import json
import csv
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.strategy_data_policy import DataGap, write_backfill_request

from .loaders import RollingInputs


REQUIRED_DATASETS = (
    "market.trading_calendar", "market.index_daily_bar", "market_daily_bar",
    "core.asset_status_daily", "core.industry_membership", "core.concept_membership",
    "market.industry_daily_bar", "market.concept_daily_bar", "finance_history",
    "valuation_history",
)


@dataclass(frozen=True)
class PreflightResult:
    blocked: bool
    data_cutoff_date: date
    checked_datasets: tuple[str, ...]
    coverage_rows: tuple[dict[str, Any], ...]
    gaps: tuple[DataGap, ...]
    status: str = "passed"
    backfill_request_path: Path | None = None


def run_rolling_preflight(
    inputs: RollingInputs | dict[str, pd.DataFrame], *, anchor_date: date, output_dir: str | Path
) -> PreflightResult:
    """Classify missing PIT database coverage and request a separate backfill."""
    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")
    if isinstance(inputs, RollingInputs) and inputs.anchor_date != anchor_date:
        raise ValueError(
            "anchor_date does not agree with inputs.anchor_date"
        )
    frames, cutoff, index_ids, score_version = _normalize_inputs(inputs, anchor_date)
    cutoff_text = cutoff.isoformat()
    gaps: list[DataGap] = []
    coverage: list[dict[str, Any]] = []

    calendar_rows = _dated_rows(frames["trading_dates"], "trade_date", anchor_date)
    coverage.append(_coverage("market.trading_calendar", expected=252, actual=len(calendar_rows)))
    if len(calendar_rows) < 252:
        gaps.append(
            DataGap(
                "market.trading_calendar",
                "__market__",
                calendar_rows[0].isoformat() if calendar_rows else None,
                cutoff_text,
                252,
                len(calendar_rows),
                "insufficient_history",
            )
        )

    index_frame = frames["index_bars"]
    configured_indexes = index_ids or _unique_values(index_frame, "index_id")
    for index_id in configured_indexes:
        actual = _count_index_sessions(index_frame, index_id, cutoff)
        coverage.append(_coverage("market.index_daily_bar", index_id, expected=252, actual=actual))
        if actual < 252:
            gaps.append(DataGap("market.index_daily_bar", index_id, None, cutoff_text, 252, actual, "insufficient_252_session_history"))

    industry_sectors = _active_sectors(frames["industry_membership"], "industry", anchor_date)
    concept_sectors = _active_sectors(frames["concept_membership"], "concept", anchor_date)
    coverage.append(_coverage("core.industry_membership", expected=len(industry_sectors), actual=len(industry_sectors)))
    coverage.append(_coverage("core.concept_membership", expected=len(concept_sectors), actual=len(concept_sectors)))
    _check_sector_bars(
        gaps,
        coverage,
        industry_sectors,
        frames["industry_bars"],
        "industry",
        cutoff,
        cutoff_keys=_sector_cutoff_keys(frames["industry_bars"], "industry", cutoff),
    )
    _check_sector_bars(
        gaps,
        coverage,
        concept_sectors,
        frames["concept_bars"],
        "concept",
        cutoff,
        cutoff_keys=_sector_cutoff_keys(frames["concept_bars"], "concept", cutoff),
    )

    assets = sorted({sector["asset_id"] for sector in industry_sectors + concept_sectors})
    stock_cutoff_assets = _assets_at_cutoff(frames["stock_bars"], cutoff)
    status_cutoff_assets = _assets_at_cutoff(frames["stock_status"], cutoff)
    stock_actual = 0
    status_actual = 0
    for asset_id in assets:
        has_bar = asset_id in stock_cutoff_assets
        has_status = asset_id in status_cutoff_assets
        stock_actual += int(has_bar)
        status_actual += int(has_status)
        if not has_bar:
            gaps.append(DataGap("market_daily_bar", asset_id, cutoff_text, cutoff_text, 1, 0, "missing_cutoff_bar"))
        if not has_status:
            gaps.append(DataGap("core.asset_status_daily", asset_id, cutoff_text, cutoff_text, 1, 0, "missing_cutoff_status"))
    coverage.append(_coverage("market_daily_bar", expected=len(assets), actual=stock_actual))
    coverage.append(_coverage("core.asset_status_daily", expected=len(assets), actual=status_actual))

    finance_actual = _check_pit_records(
        gaps,
        frames["finance"],
        assets,
        anchor_date,
        "announcement_date",
        "finance_history",
        pit_assets=_pit_assets(frames["finance"], "announcement_date", anchor_date),
    )
    valuation_actual = _check_pit_records(
        gaps,
        frames["valuation"],
        assets,
        cutoff,
        "valuation_date",
        "valuation_history",
        pit_assets=_pit_assets(frames["valuation"], "valuation_date", cutoff),
    )
    coverage.append(_coverage("finance_history", expected=len(assets), actual=finance_actual))
    coverage.append(_coverage("valuation_history", expected=len(assets), actual=valuation_actual))

    ordered_gaps = tuple(sorted(gaps, key=lambda gap: (gap.dataset, gap.asset_id, gap.start_date or "", gap.end_date or "", gap.reason)))
    _write_backfill_requests_csv(output_dir, ordered_gaps)
    request_path = None
    if ordered_gaps:
        request_path = write_backfill_request(
            output_dir,
            strategy="rolling_sector_oversold",
            trade_date=anchor_date.isoformat(),
            ranking_version=score_version or "rolling_oversold_v1",
            gaps=ordered_gaps,
        )
    result = PreflightResult(
        blocked=bool(ordered_gaps), data_cutoff_date=cutoff,
        checked_datasets=REQUIRED_DATASETS, coverage_rows=tuple(coverage), gaps=ordered_gaps,
        status="blocked_missing_data" if ordered_gaps else "passed",
        backfill_request_path=request_path,
    )
    _write_preflight_artifact(output_dir, result)
    return result


def _normalize_inputs(inputs: RollingInputs | dict[str, pd.DataFrame], anchor: date) -> tuple[dict[str, pd.DataFrame], date, tuple[str, ...], str]:
    names = (
        "trading_dates", "index_bars", "stock_bars", "stock_status", "industry_membership",
        "concept_membership", "industry_bars", "concept_bars", "finance", "valuation",
    )
    if isinstance(inputs, RollingInputs):
        frames = {name: getattr(inputs, name) for name in names}
        cutoff, index_ids, score_version = inputs.data_cutoff_date, inputs.index_ids, inputs.score_version
    elif isinstance(inputs, dict):
        frames = {name: inputs.get(name, pd.DataFrame()) for name in names}
        dates = _dated_rows(frames["trading_dates"], "trade_date", anchor)
        cutoff, index_ids, score_version = (max(dates) if dates else anchor), (), "rolling_oversold_v1"
    else:
        raise TypeError("inputs must be RollingInputs or a mapping of DataFrames")
    if not isinstance(cutoff, date):
        raise TypeError("data_cutoff_date must be a date")
    if any(not isinstance(frame, pd.DataFrame) for frame in frames.values()):
        raise TypeError("all input datasets must be pandas DataFrames")
    return frames, cutoff, tuple(index_ids), str(score_version)


def _active_sectors(frame: pd.DataFrame, prefix: str, anchor: date) -> list[dict[str, str]]:
    required = {"asset_id", f"{prefix}_system", f"{prefix}_code", f"{prefix}_name", "start_date", "end_date"}
    if not required.issubset(frame.columns):
        return []
    sectors: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in frame.to_dict(orient="records"):
        start, end = _date(row.get("start_date")), _date(row.get("end_date"))
        if start is None or start > anchor or (end is not None and end <= anchor):
            continue
        asset_id, system, code = (str(row.get(key) or "").strip() for key in ("asset_id", f"{prefix}_system", f"{prefix}_code"))
        if not asset_id or not system or not code:
            continue
        name = str(row.get(f"{prefix}_name") or "").strip()
        sectors[(asset_id, system, code, name)] = {"asset_id": asset_id, "system": system, "code": code, "name": name}
    return [sectors[key] for key in sorted(sectors)]


def _check_sector_bars(
    gaps: list[DataGap],
    coverage: list[dict[str, Any]],
    sectors: list[dict[str, str]],
    bars: pd.DataFrame,
    prefix: str,
    cutoff: date,
    *,
    cutoff_keys: set[tuple[str, str]] | None = None,
) -> None:
    dataset = f"market.{prefix}_daily_bar"
    cutoff_text = cutoff.isoformat()
    unique = {(sector["system"], sector["code"]) for sector in sectors}
    names = {
        (sector["system"], sector["code"]): sector["name"]
        for sector in sectors
    }
    for system, code in sorted(unique):
        name = names[(system, code)]
        actual = int(
            (system, code) in cutoff_keys
            if cutoff_keys is not None
            else _has_sector_cutoff_bar(bars, prefix, system, code, cutoff)
        )
        coverage.append(_coverage(dataset, f"{system}:{code}", expected=1, actual=actual, sector_code=code, sector_name=name))
        if not actual:
            gaps.append(DataGap(dataset, f"{system}:{code}", cutoff_text, cutoff_text, 1, 0, "missing_cutoff_sector_bar"))


def _check_pit_records(
    gaps: list[DataGap],
    frame: pd.DataFrame,
    assets: list[str],
    cutoff: date,
    date_column: str,
    dataset: str,
    *,
    pit_assets: set[str] | None = None,
) -> int:
    actual = 0
    cutoff_text = cutoff.isoformat()
    for asset_id in assets:
        present = (
            asset_id in pit_assets
            if pit_assets is not None
            else _has_pit_record(frame, asset_id, date_column, cutoff)
        )
        actual += int(present)
        if not present:
            gaps.append(DataGap(dataset, asset_id, None, cutoff_text, 1, 0, f"missing_pit_{dataset}_record"))
    return actual


def _coverage(dataset: str, asset_id: str | None = None, *, expected: int, actual: int, sector_code: str | None = None, sector_name: str | None = None) -> dict[str, Any]:
    return {"dataset": dataset, "asset_id": asset_id, "sector_code": sector_code, "sector_name": sector_name, "expected_rows": expected, "actual_rows": actual, "status": "covered" if actual >= expected else "gap"}


def _assets_at_cutoff(frame: pd.DataFrame, cutoff: date) -> set[str]:
    if not {"asset_id", "trade_date"}.issubset(frame.columns):
        return set()
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    values = frame.loc[dates.eq(cutoff), "asset_id"].astype("string").str.strip()
    return {str(value) for value in values.dropna() if str(value)}


def _pit_assets(frame: pd.DataFrame, date_column: str, cutoff: date) -> set[str]:
    if not {"asset_id", date_column}.issubset(frame.columns):
        return set()
    dates = pd.to_datetime(frame[date_column], errors="coerce").dt.date
    values = frame.loc[dates.le(cutoff), "asset_id"].astype("string").str.strip()
    return {str(value) for value in values.dropna() if str(value)}


def _sector_cutoff_keys(
    frame: pd.DataFrame, prefix: str, cutoff: date
) -> set[tuple[str, str]]:
    required = {f"{prefix}_system", f"{prefix}_code", "trade_date"}
    if not required.issubset(frame.columns):
        return set()
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    selected = frame.loc[
        dates.eq(cutoff), [f"{prefix}_system", f"{prefix}_code"]
    ].copy()
    if selected.empty:
        return set()
    for column in (f"{prefix}_system", f"{prefix}_code"):
        selected[column] = selected[column].astype("string").fillna("").str.strip()
    return {
        (str(row[f"{prefix}_system"]), str(row[f"{prefix}_code"]))
        for row in selected.to_dict(orient="records")
    }


def _dated_rows(frame: pd.DataFrame, column: str, cutoff: date) -> list[date]:
    if column not in frame.columns:
        return []
    return sorted({value for value in (_date(item) for item in frame[column]) if value is not None and value <= cutoff})


def _count_index_sessions(frame: pd.DataFrame, index_id: str, cutoff: date) -> int:
    if not {"index_id", "trade_date", "close"}.issubset(frame.columns):
        return 0
    dates = {_date(row.trade_date) for row in frame.loc[frame["index_id"].astype(str).eq(index_id)].itertuples(index=False) if _date(row.trade_date) is not None and _date(row.trade_date) <= cutoff and pd.notna(row.close)}
    return len(dates)


def _has_cutoff_row(frame: pd.DataFrame, asset_id: str, cutoff: date) -> bool:
    if not {"asset_id", "trade_date"}.issubset(frame.columns):
        return False
    return any(_date(row.trade_date) == cutoff for row in frame.loc[frame["asset_id"].astype(str).str.strip().eq(asset_id)].itertuples(index=False))


def _has_sector_cutoff_bar(frame: pd.DataFrame, prefix: str, system: str, code: str, cutoff: date) -> bool:
    required = {f"{prefix}_system", f"{prefix}_code", "trade_date"}
    if not required.issubset(frame.columns):
        return False
    selected = frame.loc[frame[f"{prefix}_system"].astype(str).str.strip().eq(system) & frame[f"{prefix}_code"].astype(str).str.strip().eq(code)]
    return any(_date(value) == cutoff for value in selected["trade_date"])


def _has_pit_record(frame: pd.DataFrame, asset_id: str, date_column: str, cutoff: date) -> bool:
    if not {"asset_id", date_column}.issubset(frame.columns):
        return False
    selected = frame.loc[frame["asset_id"].astype(str).str.strip().eq(asset_id), date_column]
    return any(value is not None and value <= cutoff for value in (_date(value) for value in selected))


def _unique_values(frame: pd.DataFrame, column: str) -> tuple[str, ...]:
    if column not in frame.columns:
        return ()
    return tuple(sorted({str(value).strip() for value in frame[column] if str(value).strip()}))


def _date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _write_preflight_artifact(output_dir: str | Path, result: PreflightResult) -> Path:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    payload = {"blocked": result.blocked, "status": result.status, "data_cutoff_date": result.data_cutoff_date.isoformat(), "checked_datasets": list(result.checked_datasets), "coverage_rows": list(result.coverage_rows), "gaps": [asdict(gap) for gap in result.gaps], "backfill_request_path": str(result.backfill_request_path) if result.backfill_request_path else None}
    path = destination / "preflight.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_backfill_requests_csv(output_dir: str | Path, gaps: tuple[DataGap, ...]) -> Path:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "backfill_requests.csv"
    columns = (
        "dataset", "asset_id", "start_date", "end_date", "expected_rows",
        "actual_rows", "reason",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(asdict(gap) for gap in gaps)
    return path
