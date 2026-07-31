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

    gaps: list[DataGap] = []
    for row in included_rows.to_dict(orient="records"):
        asset_id = str(row["asset_id"])
        list_date = _parse_optional_date(row.get("list_date"))
        required_sessions = _required_market_sessions(list_date, cutoff)
        asset_bars = _asset_rows(bars, asset_id)
        asset_bars = _valid_before(asset_bars, "trade_date", cutoff)
        if not _has_required_columns(asset_bars, ("trade_date", "close")):
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
            actual = int(
                asset_bars.loc[
                    pd.to_numeric(asset_bars["close"], errors="coerce")
                    .replace([np.inf, -np.inf], np.nan)
                    .notna()
                , "trade_date"].nunique()
            )
            latest = _latest_date(asset_bars, "trade_date")
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

        asset_shares = _asset_rows(share_capacity, asset_id)
        if not _has_positive_single_row(asset_shares, ("total_share", "float_share")):
            gaps.append(
                DataGap(
                    "share_capacity",
                    asset_id,
                    cutoff.isoformat(),
                    cutoff.isoformat(),
                    1,
                    int(len(asset_shares)),
                    "missing_positive_share_capacity",
                )
            )

        asset_finance = _asset_rows(finance, asset_id)
        asset_finance = _valid_before(asset_finance, "announcement_date", cutoff)
        if not _has_nonempty_rows(asset_finance, ("report_period", "announcement_date")):
            gaps.append(
                DataGap(
                    "finance_history",
                    asset_id,
                    None,
                    cutoff.isoformat(),
                    1,
                    int(len(asset_finance)),
                    "missing_pit_finance_record",
                )
            )

        asset_valuation = _asset_rows(valuation_history, asset_id)
        asset_valuation = _valid_before(asset_valuation, "valuation_date", cutoff)
        if not _has_nonempty_rows(asset_valuation, ("valuation_date",)):
            gaps.append(
                DataGap(
                    "valuation_history",
                    asset_id,
                    None,
                    cutoff.isoformat(),
                    1,
                    int(len(asset_valuation)),
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


def _required_market_sessions(list_date: date | None, cutoff: date) -> int:
    if list_date is None or list_date >= cutoff:
        return 1
    return min(REQUIRED_MARKET_HISTORY_SESSIONS, max(1, (cutoff - list_date).days + 1))


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
