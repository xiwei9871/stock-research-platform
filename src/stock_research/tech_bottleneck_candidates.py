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
) -> pd.DataFrame:
    start_date = _normalize_date_arg(start_date, name="start_date")
    end_date = _normalize_date_arg(end_date, name="end_date")
    _validate_date_order(start_date, end_date)
    candidates = _normalize_base_candidates(base_candidates)
    normalized_prices = _normalize_prices(prices, start_date=start_date, end_date=end_date)
    trading_dates = sorted(normalized_prices["trade_date"].dropna().astype(str).unique().tolist())
    trading_dates = [date for date in trading_dates if start_date <= date <= end_date]
    if not trading_dates or candidates.empty:
        return pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)

    closes = normalized_prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    high_120 = closes.rolling(120, min_periods=3).max()
    rows: list[dict[str, Any]] = []

    for trade_date in trading_dates:
        eligible = candidates[
            (candidates["first_hit_date"] <= trade_date)
            & (candidates["financial_as_of_date"] <= trade_date)
            & (candidates["technical_as_of_date"] <= trade_date)
            & (candidates["candidate_as_of_date"] <= trade_date)
        ]
        eligible = eligible[eligible["asset_id"].isin(_priced_assets_for_day(closes, trade_date))]
        if eligible.empty:
            continue
        eligible = (
            eligible.sort_values(["asset_id", "candidate_as_of_date"])
            .groupby("asset_id", as_index=False, sort=False)
            .tail(1)
        )
        max_evidence = float(np.log1p(eligible["hit_count_as_of_date"]).max())
        max_evidence = max(max_evidence, 1.0)
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
                    "hit_count_as_of_date": float(row.hit_count_as_of_date),
                    "primary_chain_id": str(getattr(row, "primary_chain_id", "") or ""),
                    "primary_chain_name": str(getattr(row, "primary_chain_name", "") or ""),
                    "matched_bottleneck_dimensions": str(getattr(row, "matched_bottleneck_dimensions", "") or ""),
                    "financial_as_of_date": str(row.financial_as_of_date),
                    "technical_as_of_date": str(row.technical_as_of_date),
                    "data_as_of_date": trade_date,
                    "filter_decision": "pass",
                    "filter_reason": str(getattr(row, "filter_reason", "") or ""),
                    "bottleneck_score": score,
                    "engine_version": TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
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
    for column in ["asset_id", "engine_version", "run_id"]:
        if _is_missing_or_empty(normalized[column]).any():
            raise ValueError(f"{column} must be non-empty")
    bad_engine = normalized["engine_version"].astype(str) != TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION
    if bool(bad_engine.any()):
        raise ValueError(f"engine_version must equal {TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION}")
    date_columns = ["trade_date", "first_hit_date", "financial_as_of_date", "technical_as_of_date", "data_as_of_date"]
    for column in date_columns:
        normalized[column] = _parse_required_date_column(
            normalized[column],
            invalid_message=f"invalid date in candidate snapshot: {column}",
        )
    normalized["hit_count_as_of_date"] = _numeric_required_column(
        normalized["hit_count_as_of_date"],
        invalid_message="hit_count_as_of_date must be numeric",
    )
    normalized["bottleneck_score"] = _numeric_required_column(
        normalized["bottleneck_score"],
        invalid_message="bottleneck_score must be numeric",
    )
    normalized["bottleneck_rank"] = _numeric_required_column(
        normalized["bottleneck_rank"],
        invalid_message="bottleneck_rank must be numeric",
    )
    _validate_finite_nonnegative(
        normalized["hit_count_as_of_date"],
        column="hit_count_as_of_date",
    )
    _validate_finite_nonnegative(
        normalized["bottleneck_score"],
        column="bottleneck_score",
    )
    _validate_positive_integer_rank(normalized["bottleneck_rank"])

    checks = [
        ("first_hit_date", "first_hit_date must be <= trade_date"),
        ("financial_as_of_date", "financial_as_of_date must be <= trade_date"),
        ("technical_as_of_date", "technical_as_of_date must be <= trade_date"),
    ]
    for column, message in checks:
        bad = normalized[column] > normalized["trade_date"]
        if bool(bad.any()):
            raise ValueError(message)
    stale_data_as_of = normalized["data_as_of_date"] != normalized["trade_date"]
    if bool(stale_data_as_of.any()):
        raise ValueError("data_as_of_date must equal trade_date")
    duplicates = normalized.duplicated(subset=["trade_date", "asset_id"], keep=False)
    if bool(duplicates.any()):
        raise ValueError("duplicate candidate snapshot rows for trade_date and asset_id")
    duplicate_ranks = normalized.duplicated(subset=["trade_date", "bottleneck_rank"], keep=False)
    if bool(duplicate_ranks.any()):
        raise ValueError("duplicate bottleneck_rank within trade_date")
    for trade_date, day in normalized.groupby("trade_date", sort=False):
        ranks = sorted(int(rank) for rank in day["bottleneck_rank"].tolist())
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("bottleneck_rank must be contiguous within trade_date")
    expected_order = normalized.sort_values(
        ["trade_date", "bottleneck_score", "hit_count_as_of_date", "asset_id"],
        ascending=[True, False, False, True],
    )
    expected_ranks = expected_order.groupby("trade_date").cumcount() + 1
    if bool((normalized.loc[expected_order.index, "bottleneck_rank"].to_numpy() != expected_ranks.to_numpy()).any()):
        raise ValueError("bottleneck_rank must match score ordering")
    expected_top5 = normalized["bottleneck_rank"] <= 5
    actual_top5 = _parse_bool_column(normalized["is_top5"], invalid_message="is_top5 must be boolean")
    if bool((actual_top5 != expected_top5).any()):
        raise ValueError("is_top5 must equal bottleneck_rank <= 5")
    invalid_filter = ~normalized["filter_decision"].isin(["pass", "fail"])
    if bool(invalid_filter.any()):
        raise ValueError("filter_decision must be one of: pass, fail")


def write_candidate_snapshots(frame: pd.DataFrame, path: str | Path) -> Path:
    validate_candidate_snapshot_frame(frame)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def read_candidate_snapshots(path: str | Path, *, start_date: str, end_date: str) -> pd.DataFrame:
    start_date = _normalize_date_arg(start_date, name="start_date")
    end_date = _normalize_date_arg(end_date, name="end_date")
    _validate_date_order(start_date, end_date)
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
    end_date = _normalize_date_arg(end_date, name="end_date")
    if frame.empty:
        raise ValueError("base candidate source is empty")
    coverage_columns = ["source_latest_trade_date", "data_as_of_date"]
    parsed_coverage: dict[str, pd.Series] = {}
    for column in coverage_columns:
        if column in frame.columns:
            parsed = _parse_required_date_column(
                frame[column],
                invalid_message=f"invalid base candidate freshness metadata: {column}",
            )
            stale = parsed < end_date
            if bool(stale.any()):
                oldest = str(parsed[stale].min())
                raise ValueError(f"base candidate source is stale: {oldest} < {end_date}")
            parsed_coverage[column] = parsed
    if "generated_trade_date" in frame.columns:
        generated = _parse_required_date_column(
            frame["generated_trade_date"],
            invalid_message="invalid base candidate freshness metadata: generated_trade_date",
        )
        stale_generated = generated < end_date
        if bool(stale_generated.any()):
            oldest_generated = str(generated[stale_generated].min())
            raise ValueError(f"generated_trade_date is stale: {oldest_generated} < {end_date}")
        for column, coverage in parsed_coverage.items():
            contradictory = generated < coverage
            if bool(contradictory.any()):
                raise ValueError("generated_trade_date must be >= coverage date")
    if not parsed_coverage:
        raise ValueError("base candidate source freshness metadata missing")


def _normalize_base_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "stock_name",
                "first_hit_date",
                "hit_count",
                "hit_count_as_of_date",
                "candidate_as_of_date",
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
    frame["first_hit_date"] = _parse_required_date_column(
        frame["first_hit_date"],
        invalid_message="invalid base candidate date: first_hit_date",
    )
    candidate_date_column = _candidate_date_column(frame)
    if candidate_date_column is not None:
        frame["candidate_as_of_date"] = _parse_required_date_column(
            frame[candidate_date_column],
            invalid_message=f"invalid base candidate date: {candidate_date_column}",
        )
    else:
        raise ValueError("candidate_as_of_date missing: provide trade_date or candidate_trade_date")

    if "hit_count_as_of_date" in frame.columns and candidate_date_column is not None:
        frame["hit_count_as_of_date"] = _numeric_required_column(
            frame["hit_count_as_of_date"],
            invalid_message="hit_count_as_of_date must be numeric",
        )
        frame["filter_reason"] = _string_column(frame, "filter_reason")
    else:
        frame["hit_count_as_of_date"] = 1.0
        existing_reason = _string_column(frame, "filter_reason")
        frame["filter_reason"] = existing_reason.where(
            existing_reason.str.strip().ne(""),
            "static_source_hit_count_conservative_1",
        )
    for column in ["primary_chain_id", "primary_chain_name", "matched_bottleneck_dimensions"]:
        frame[column] = _string_column(frame, column)
    if "financial_as_of_date" not in frame.columns:
        frame["financial_as_of_date"] = frame["first_hit_date"]
    if "technical_as_of_date" not in frame.columns:
        frame["technical_as_of_date"] = frame["first_hit_date"]
    frame["financial_as_of_date"] = _parse_required_date_column(
        frame["financial_as_of_date"],
        invalid_message="invalid base candidate date: financial_as_of_date",
    )
    frame["technical_as_of_date"] = _parse_required_date_column(
        frame["technical_as_of_date"],
        invalid_message="invalid base candidate date: technical_as_of_date",
    )
    return frame.dropna(subset=["asset_id", "first_hit_date", "financial_as_of_date", "technical_as_of_date"])


def _normalize_prices(prices: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "open", "high", "low", "close"])

    frame = prices.copy()
    missing_price_columns = [column for column in ["open", "high", "low", "close"] if column not in frame.columns]
    if missing_price_columns:
        raise ValueError(f"price input missing columns: {missing_price_columns}")
    frame["trade_date"] = _parse_required_date_column(
        frame["trade_date"],
        invalid_message="invalid price date: trade_date",
    )
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame = frame[frame["trade_date"].le(end_date)]
    duplicates = frame.duplicated(subset=["trade_date", "asset_id"], keep=False)
    if bool(duplicates.any()):
        raise ValueError("duplicate price rows for trade_date and asset_id")
    for column in ["open", "close"]:
        frame[column] = _parse_price_numeric_column(frame[column], column=column)
    frame["high"] = _parse_price_numeric_column(frame["high"], column="high")
    frame["low"] = _parse_price_numeric_column(frame["low"], column="low")
    _validate_positive_price_column(frame["open"], column="open")
    _validate_positive_price_column(frame["close"], column="close")
    _validate_positive_price_column(frame["high"], column="high")
    _validate_positive_price_column(frame["low"], column="low")
    _validate_ohlc_consistency(frame)
    return frame.dropna(subset=["trade_date", "asset_id"]).sort_values(["trade_date", "asset_id"])


def _bottleneck_score(*, row: Any, trade_date: str, closes: pd.DataFrame, high_120: pd.DataFrame, max_evidence: float) -> float:
    evidence_norm = float(np.log1p(float(row.hit_count_as_of_date)) / max_evidence)
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


def _priced_assets_for_day(closes: pd.DataFrame, trade_date: str) -> set[str]:
    if trade_date not in closes.index:
        return set()
    row = closes.loc[trade_date]
    return {str(asset_id) for asset_id, close in row.items() if pd.notna(close)}


def _string_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str)


def _parse_required_date_column(values: pd.Series, *, invalid_message: str) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if bool(parsed.isna().any()):
        raise ValueError(invalid_message)
    return parsed.dt.strftime("%Y-%m-%d")


def _normalize_date_arg(value: str, *, name: str) -> str:
    parsed = pd.to_datetime(pd.Series([value]), errors="coerce")
    if bool(parsed.isna().any()):
        raise ValueError(f"invalid date: {name}")
    return str(parsed.dt.strftime("%Y-%m-%d").iloc[0])


def _validate_date_order(start_date: str, end_date: str) -> None:
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")


def _numeric_required_column(values: pd.Series, *, invalid_message: str) -> pd.Series:
    parsed = pd.to_numeric(values, errors="coerce")
    if bool(parsed.isna().any()):
        raise ValueError(invalid_message)
    return parsed


def _parse_price_numeric_column(values: pd.Series, *, column: str) -> pd.Series:
    parsed = pd.to_numeric(values, errors="coerce")
    if bool(parsed.isna().any()):
        raise ValueError(f"{column} must be numeric")
    finite = np.isfinite(parsed.astype(float))
    if bool((~finite).any()):
        raise ValueError(f"{column} must be finite")
    return parsed


def _validate_positive_price_column(values: pd.Series, *, column: str) -> None:
    if bool((values <= 0).any()):
        raise ValueError(f"{column} must be > 0")


def _validate_ohlc_consistency(frame: pd.DataFrame) -> None:
    if bool((frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any()):
        raise ValueError("high must be >= max(open, close, low)")
    if bool((frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("low must be <= min(open, close, high)")


def _validate_finite_nonnegative(values: pd.Series, *, column: str) -> None:
    finite = np.isfinite(values.astype(float))
    if bool((~finite).any()):
        raise ValueError(f"{column} must be finite")
    if bool((values < 0).any()):
        raise ValueError(f"{column} must be >= 0")


def _validate_positive_integer_rank(values: pd.Series) -> None:
    finite = np.isfinite(values.astype(float))
    if bool((~finite).any()):
        raise ValueError("bottleneck_rank must be finite")
    positive_integer = (values > 0) & (values % 1 == 0)
    if bool((~positive_integer).any()):
        raise ValueError("bottleneck_rank must be finite positive integer")


def _parse_bool_column(values: pd.Series, *, invalid_message: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values
    normalized = values.astype(str).str.lower()
    mapping = {"true": True, "false": False}
    parsed = normalized.map(mapping)
    if bool(parsed.isna().any()):
        raise ValueError(invalid_message)
    return parsed


def _is_missing_or_empty(values: pd.Series) -> pd.Series:
    return values.isna() | values.astype(str).str.strip().eq("")


def _candidate_date_column(frame: pd.DataFrame) -> str | None:
    if "candidate_trade_date" in frame.columns:
        return "candidate_trade_date"
    if "trade_date" in frame.columns:
        return "trade_date"
    return None
