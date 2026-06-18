from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION = "tech_bottleneck_daily_candidates_v1"
TECH_BOTTLENECK_CANDIDATE_SOURCE = "point_in_time_daily_candidates"
TECH_BOTTLENECK_CANDIDATE_COLUMNS = [
    "trade_date",
    "asset_id",
    "stock_name",
    "first_hit_date",
    "hit_count_as_of_date",
    "primary_chain_id",
    "primary_chain_name",
    "matched_bottleneck_dimensions",
    "financial_as_of_date",
    "technical_as_of_date",
    "data_as_of_date",
    "filter_decision",
    "filter_reason",
    "bottleneck_score",
    "bottleneck_rank",
    "is_top5",
    "engine_version",
    "run_id",
]


def build_point_in_time_candidate_snapshots(
    *,
    base_candidates: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    run_id: str,
    engine_version: str = TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
) -> pd.DataFrame:
    candidates = _normalize_base_candidates(base_candidates)
    normalized_prices = _normalize_prices(prices, start_date=start_date, end_date=end_date)
    trading_dates = sorted(normalized_prices["trade_date"].dropna().astype(str).unique().tolist())
    trading_dates = [date for date in trading_dates if start_date <= date <= end_date]
    if not trading_dates or candidates.empty:
        return pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)

    closes = normalized_prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    high_120 = closes.rolling(120, min_periods=3).max()
    max_evidence = float(np.log1p(pd.to_numeric(candidates["hit_count"], errors="coerce").fillna(1)).max())
    max_evidence = max(max_evidence, 1.0)
    rows: list[dict[str, Any]] = []

    for trade_date in trading_dates:
        eligible = candidates[
            (candidates["first_hit_date"] <= trade_date)
            & (candidates["financial_as_of_date"] <= trade_date)
            & (candidates["technical_as_of_date"] <= trade_date)
        ]
        for row in eligible.itertuples(index=False):
            asset_id = str(row.asset_id)
            score = _bottleneck_score(
                row=row,
                trade_date=trade_date,
                closes=closes,
                high_120=high_120,
                max_evidence=max_evidence,
            )
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "stock_name": str(getattr(row, "stock_name", "") or ""),
                    "first_hit_date": str(row.first_hit_date),
                    "hit_count_as_of_date": float(row.hit_count),
                    "primary_chain_id": str(getattr(row, "primary_chain_id", "") or ""),
                    "primary_chain_name": str(getattr(row, "primary_chain_name", "") or ""),
                    "matched_bottleneck_dimensions": str(getattr(row, "matched_bottleneck_dimensions", "") or ""),
                    "financial_as_of_date": str(row.financial_as_of_date),
                    "technical_as_of_date": str(row.technical_as_of_date),
                    "data_as_of_date": trade_date,
                    "filter_decision": "pass",
                    "filter_reason": "",
                    "bottleneck_score": score,
                    "engine_version": engine_version,
                    "run_id": str(run_id),
                }
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)
    frame = frame.sort_values(
        ["trade_date", "bottleneck_score", "hit_count_as_of_date", "asset_id"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    frame["bottleneck_rank"] = frame.groupby("trade_date").cumcount() + 1
    frame["is_top5"] = frame["bottleneck_rank"] <= 5
    frame = frame[TECH_BOTTLENECK_CANDIDATE_COLUMNS]
    validate_candidate_snapshot_frame(frame)
    return frame


def validate_candidate_snapshot_frame(frame: pd.DataFrame) -> None:
    missing = [column for column in TECH_BOTTLENECK_CANDIDATE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"candidate snapshot missing columns: {missing}")
    if frame.empty:
        return

    normalized = frame.copy()
    date_columns = ["trade_date", "first_hit_date", "financial_as_of_date", "technical_as_of_date", "data_as_of_date"]
    for column in date_columns:
        normalized[column] = pd.to_datetime(normalized[column], errors="coerce").dt.strftime("%Y-%m-%d")

    checks = [
        ("first_hit_date", "first_hit_date must be <= trade_date"),
        ("financial_as_of_date", "financial_as_of_date must be <= trade_date"),
        ("technical_as_of_date", "technical_as_of_date must be <= trade_date"),
        ("data_as_of_date", "data_as_of_date must be <= trade_date"),
    ]
    for column, message in checks:
        bad = normalized[column] > normalized["trade_date"]
        if bool(bad.any()):
            raise ValueError(message)


def write_candidate_snapshots(frame: pd.DataFrame, path: str | Path) -> Path:
    validate_candidate_snapshot_frame(frame)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def read_candidate_snapshots(path: str | Path, *, start_date: str, end_date: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    validate_candidate_snapshot_frame(frame)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame[frame["trade_date"].between(start_date, end_date)].copy()
    return frame.sort_values(["trade_date", "bottleneck_rank", "asset_id"]).reset_index(drop=True)


def read_base_candidate_source(path: str | Path, *, end_date: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    validate_base_candidate_source_freshness(frame, end_date=end_date)
    return frame


def validate_base_candidate_source_freshness(frame: pd.DataFrame, *, end_date: str) -> None:
    if frame.empty:
        raise ValueError("base candidate source is empty")
    for column in ["source_latest_trade_date", "data_as_of_date", "generated_trade_date"]:
        if column in frame.columns:
            latest = str(pd.to_datetime(frame[column], errors="coerce").dt.strftime("%Y-%m-%d").max())
            if latest >= end_date:
                return
            raise ValueError(f"base candidate source is stale: {latest} < {end_date}")
    if "first_hit_date" in frame.columns:
        latest_first_hit = str(pd.to_datetime(frame["first_hit_date"], errors="coerce").dt.strftime("%Y-%m-%d").max())
        if latest_first_hit >= end_date:
            return
    raise ValueError("base candidate source is stale: no freshness column covers requested end_date")


def _normalize_base_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "stock_name",
                "first_hit_date",
                "hit_count",
                "primary_chain_id",
                "primary_chain_name",
                "matched_bottleneck_dimensions",
                "financial_as_of_date",
                "technical_as_of_date",
            ]
        )

    frame = candidates.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["stock_name"] = _string_column(frame, "stock_name")
    frame["first_hit_date"] = pd.to_datetime(frame["first_hit_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "hit_count" not in frame.columns:
        frame["hit_count"] = 1.0
    frame["hit_count"] = pd.to_numeric(frame["hit_count"], errors="coerce").fillna(1.0)
    for column in ["primary_chain_id", "primary_chain_name", "matched_bottleneck_dimensions"]:
        frame[column] = _string_column(frame, column)
    if "financial_as_of_date" not in frame.columns:
        frame["financial_as_of_date"] = frame["first_hit_date"]
    if "technical_as_of_date" not in frame.columns:
        frame["technical_as_of_date"] = frame["first_hit_date"]
    frame["financial_as_of_date"] = pd.to_datetime(frame["financial_as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["technical_as_of_date"] = pd.to_datetime(frame["technical_as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame.dropna(subset=["asset_id", "first_hit_date", "financial_as_of_date", "technical_as_of_date"])


def _normalize_prices(prices: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "open", "high", "low", "close"])

    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ["open", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "high" not in frame.columns:
        frame["high"] = frame[["open", "close"]].max(axis=1)
    if "low" not in frame.columns:
        frame["low"] = frame[["open", "close"]].min(axis=1)
    frame["high"] = pd.to_numeric(frame["high"], errors="coerce")
    frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)]
    return frame.dropna(subset=["trade_date", "asset_id", "close"]).sort_values(["trade_date", "asset_id"])


def _bottleneck_score(*, row: Any, trade_date: str, closes: pd.DataFrame, high_120: pd.DataFrame, max_evidence: float) -> float:
    evidence_norm = float(np.log1p(float(row.hit_count)) / max_evidence)
    age_days = max((pd.Timestamp(trade_date) - pd.Timestamp(row.first_hit_date)).days, 0)
    freshness = max(0.0, 1.0 - age_days / 240.0)
    low_position = 0.5
    asset_id = str(row.asset_id)
    if asset_id in closes.columns and trade_date in closes.index:
        close = closes.at[trade_date, asset_id]
        rolling_high = high_120.at[trade_date, asset_id] if asset_id in high_120.columns else np.nan
        if pd.notna(close) and pd.notna(rolling_high) and rolling_high > 0:
            low_position = float(max(0.0, min(1.0, 1.0 - close / rolling_high)))
    return float(0.45 * evidence_norm + 0.25 * freshness + 0.30 * low_position)


def _string_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str)
