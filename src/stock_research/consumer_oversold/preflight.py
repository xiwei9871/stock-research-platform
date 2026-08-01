from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from stock_research.strategy_data_policy import DataGap


REQUIRED_MARKET_HISTORY_SESSIONS = 504
REQUIRED_DATASETS = (
    "daily_bars",
    "share_capacity",
    "finance_history",
    "valuation_history",
)


@dataclass(frozen=True)
class PreflightResult:
    status: str
    gaps: tuple[DataGap, ...]
    checked_assets: int
    checked_datasets: tuple[str, ...] = REQUIRED_DATASETS


def run_consumer_preflight(
    *,
    included: pd.DataFrame,
    bars: pd.DataFrame,
    share_capacity: pd.DataFrame,
    finance: pd.DataFrame,
    valuation_history: pd.DataFrame,
    trade_date: str,
) -> PreflightResult:
    """Fail closed when required PIT database inputs are absent or stale."""
    cutoff = _parse_date(trade_date)
    if not isinstance(included, pd.DataFrame):
        raise TypeError("included must be a pandas DataFrame")
    if "asset_id" not in included.columns:
        raise ValueError("included missing required column: asset_id")
    included_rows = included.copy(deep=True)
    included_rows["asset_id"] = included_rows["asset_id"].astype(str).str.strip()
    included_rows = included_rows.loc[included_rows["asset_id"].ne("")]
    included_rows = included_rows.drop_duplicates("asset_id", keep="first")

    available_dates = _available_market_dates(bars, cutoff)
    market_stats = _market_stats(bars, cutoff)
    share_stats = _share_stats(share_capacity)
    finance_stats = _dated_record_stats(
        finance,
        cutoff,
        date_column="announcement_date",
        required_columns=("report_period", "announcement_date"),
    )
    valuation_stats = _dated_record_stats(
        valuation_history,
        cutoff,
        date_column="valuation_date",
        required_columns=("valuation_date",),
    )

    gaps: list[DataGap] = []
    for row in included_rows.to_dict(orient="records"):
        asset_id = str(row["asset_id"])
        list_date = _parse_optional_date(row.get("list_date"))
        required_sessions = _required_market_sessions(
            list_date,
            cutoff,
            available_dates=available_dates,
        )
        market_stat = market_stats.get(asset_id)
        if market_stat is None:
            gaps.append(
                DataGap(
                    "daily_bars",
                    asset_id,
                    list_date.isoformat() if list_date else None,
                    cutoff.isoformat(),
                    required_sessions,
                    0,
                    "missing_required_columns_or_rows",
                )
            )
        else:
            actual, latest = market_stat
            if actual < required_sessions or latest != cutoff:
                reason = "insufficient_history" if actual < required_sessions else "missing_cutoff_bar"
                gaps.append(
                    DataGap(
                        "daily_bars",
                        asset_id,
                        list_date.isoformat() if list_date else None,
                        cutoff.isoformat(),
                        required_sessions,
                        actual,
                        reason,
                    )
                )

        share_stat = share_stats.get(asset_id)
        if share_stat is None:
            gaps.append(
                DataGap(
                    "share_capacity",
                    asset_id,
                    cutoff.isoformat(),
                    cutoff.isoformat(),
                    1,
                    0,
                    "missing_positive_share_capacity",
                )
            )

        finance_count = finance_stats.get(asset_id, 0)
        if finance_count <= 0:
            gaps.append(
                DataGap(
                    "finance_history",
                    asset_id,
                    None,
                    cutoff.isoformat(),
                    1,
                    int(finance_count),
                    "missing_pit_finance_record",
                )
            )

        valuation_count = valuation_stats.get(asset_id, 0)
        if valuation_count <= 0:
            gaps.append(
                DataGap(
                    "valuation_history",
                    asset_id,
                    None,
                    cutoff.isoformat(),
                    1,
                    int(valuation_count),
                    "missing_pit_valuation_record",
                )
            )

    ordered = tuple(
        sorted(
            gaps,
            key=lambda gap: (
                gap.dataset,
                gap.asset_id,
                gap.start_date or "",
                gap.end_date or "",
                gap.reason,
            ),
        )
    )
    return PreflightResult(
        status="blocked_missing_data" if ordered else "passed",
        gaps=ordered,
        checked_assets=int(len(included_rows)),
    )


def _asset_rows(frame: pd.DataFrame, asset_id: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or "asset_id" not in frame.columns:
        return pd.DataFrame()
    return frame.loc[frame["asset_id"].astype(str).str.strip().eq(asset_id)].copy()


def _market_stats(
    frame: pd.DataFrame,
    cutoff: date,
) -> dict[str, tuple[int, date | None]]:
    required = {"asset_id", "trade_date", "close"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        return {}
    work = frame.loc[:, ["asset_id", "trade_date", "close"]].copy()
    work["asset_id"] = work["asset_id"].astype(str).str.strip()
    work["trade_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.loc[
        work["asset_id"].ne("")
        & work["trade_date"].notna()
        & work["trade_date"].le(pd.Timestamp(cutoff))
        & work["close"].replace([np.inf, -np.inf], np.nan).notna()
    ]
    if work.empty:
        return {}
    grouped = work.groupby("asset_id", sort=False).agg(
        actual_rows=("trade_date", "nunique"),
        latest_date=("trade_date", "max"),
    )
    return {
        str(asset_id): (int(row.actual_rows), row.latest_date.date())
        for asset_id, row in grouped.iterrows()
    }


def _share_stats(frame: pd.DataFrame) -> dict[str, bool]:
    required = {"asset_id", "total_share", "float_share"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        return {}
    work = frame.loc[:, ["asset_id", "total_share", "float_share"]].copy()
    work["asset_id"] = work["asset_id"].astype(str).str.strip()
    for column in ("total_share", "float_share"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.loc[
        work["asset_id"].ne("")
        & work["total_share"].replace([np.inf, -np.inf], np.nan).gt(0.0)
        & work["float_share"].replace([np.inf, -np.inf], np.nan).gt(0.0)
    ]
    return {str(asset_id): True for asset_id in work["asset_id"].drop_duplicates()}


def _dated_record_stats(
    frame: pd.DataFrame,
    cutoff: date,
    *,
    date_column: str,
    required_columns: tuple[str, ...],
) -> dict[str, int]:
    required = {"asset_id", *required_columns}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        return {}
    work = frame.loc[:, ["asset_id", *required_columns]].copy()
    work["asset_id"] = work["asset_id"].astype(str).str.strip()
    parsed_date = pd.to_datetime(work[date_column], errors="coerce")
    valid = work["asset_id"].ne("") & parsed_date.notna() & parsed_date.le(pd.Timestamp(cutoff))
    for column in required_columns:
        valid &= work[column].notna()
    work = work.loc[valid]
    if work.empty:
        return {}
    return {
        str(asset_id): int(count)
        for asset_id, count in work.groupby("asset_id", sort=False).size().items()
    }


def _has_required_columns(frame: pd.DataFrame, columns: Iterable[str]) -> bool:
    return isinstance(frame, pd.DataFrame) and all(column in frame.columns for column in columns)


def _has_nonempty_rows(frame: pd.DataFrame, columns: Iterable[str]) -> bool:
    if not _has_required_columns(frame, columns) or frame.empty:
        return False
    return bool(frame.loc[:, list(columns)].notna().all(axis=1).any())


def _has_positive_single_row(frame: pd.DataFrame, columns: Iterable[str]) -> bool:
    if not _has_required_columns(frame, columns) or frame.empty:
        return False
    values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")
    values = values.replace([np.inf, -np.inf], np.nan)
    return bool(values.gt(0.0).all(axis=1).any())


def _valid_before(frame: pd.DataFrame, column: str, cutoff: date) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or column not in frame.columns:
        return pd.DataFrame()
    parsed = pd.to_datetime(frame[column], errors="coerce")
    return frame.loc[parsed.notna() & parsed.le(pd.Timestamp(cutoff))].copy()


def _latest_date(frame: pd.DataFrame, column: str) -> date | None:
    if not _has_required_columns(frame, (column,)) or frame.empty:
        return None
    parsed = pd.to_datetime(frame[column], errors="coerce").dropna()
    if parsed.empty:
        return None
    return parsed.max().date()


def _required_market_sessions(
    list_date: date | None,
    cutoff: date,
    *,
    available_dates: tuple[date, ...],
) -> int:
    if list_date is None or list_date >= cutoff:
        return 1
    sessions = sum(list_date <= value <= cutoff for value in available_dates)
    if sessions <= 0:
        return 1
    return min(REQUIRED_MARKET_HISTORY_SESSIONS, sessions)


def _available_market_dates(frame: pd.DataFrame, cutoff: date) -> tuple[date, ...]:
    if not isinstance(frame, pd.DataFrame) or "trade_date" not in frame.columns:
        return ()
    parsed = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    dates = sorted({value.date() for value in parsed if value.date() <= cutoff})
    return tuple(dates)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("trade_date must use YYYY-MM-DD") from exc


def _parse_optional_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None
