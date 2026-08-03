"""Forward-return evaluation for immutable rolling oversold snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from math import isfinite
from numbers import Real

import pandas as pd


_DETAIL_COLUMNS = (
    "snapshot_id",
    "anchor_date",
    "evaluation_cutoff",
    "asset_id",
    "sector_system",
    "sector_code",
    "sector_name",
    "sector_gate_status",
    "sector_recovery_state",
    "market_regime",
    "stock_lifecycle",
    "stock_rank",
    "anchor_close",
    "adjusted_close_source",
    "forward_horizon_days",
    "forward_endpoint_date",
    "forward_endpoint_close",
    "forward_Nd_return",
    "forward_Nd_status",
    "hit_3pct",
    "hit_5pct",
    "hit_7pct",
    "evaluation_status",
    "data_status",
    "data_error",
)
_SUMMARY_COLUMNS = (
    "group_by",
    "group_value",
    "forward_horizon_days",
    "total_count",
    "complete_count",
    "pending_count",
    "excluded_count",
    "data_error_count",
    "up_ratio",
    "mean_return",
    "median_return",
    "p25_return",
    "p75_return",
    "p90_return",
    "hit_3pct_rate",
    "hit_5pct_rate",
    "hit_7pct_rate",
)
_CONTEXT_COLUMNS = (
    "sector_system",
    "sector_code",
    "sector_name",
    "sector_gate_status",
    "sector_research_eligibility",
    "sector_recovery_state",
    "stock_lifecycle",
    "stock_rank",
)
_SECTOR_DETAIL_COLUMNS = (
    *_DETAIL_COLUMNS,
    "sector_stock_rank",
    "sector_rank",
    "sector_research_eligibility",
    "target_trade_date",
    "endpoint_close",
    "status",
)
_PRICE_SOURCE_COLUMNS = {
    "raw": ("raw_close",),
    "qfq": ("qfq_close",),
    "hfq": ("hfq_close",),
}
_PRICE_SOURCES = frozenset(_PRICE_SOURCE_COLUMNS)


def evaluate_snapshot(
    snapshot: dict[str, object],
    *,
    bars: pd.DataFrame,
    evaluation_cutoff: date,
    horizons: Sequence[int] = (1, 3, 5),
    allow_duplicate_assets: bool = False,
    _sector_eligibility_mode: bool = False,
) -> pd.DataFrame:
    """Evaluate only bars strictly after anchor_date and not after evaluation_cutoff.

    The snapshot supplies the anchor close.  It is intentionally never read
    from ``bars`` so a later price reload cannot alter the entry price used by
    an immutable snapshot.
    """

    normalized_horizons = _normalize_horizons(horizons)
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dictionary")
    anchor = _normalize_date(snapshot.get("anchor_date"), "snapshot anchor_date")
    cutoff = _normalize_date(evaluation_cutoff, "evaluation_cutoff")
    if cutoff < anchor:
        raise ValueError("evaluation_cutoff must not precede snapshot anchor_date")
    snapshot_id = _require_nonempty_text(snapshot.get("snapshot_id"), "snapshot snapshot_id")
    candidates = snapshot.get("stock_candidates")
    if not isinstance(candidates, pd.DataFrame):
        raise TypeError("snapshot stock_candidates must be a pandas DataFrame")
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("bars must be a pandas DataFrame")
    candidate_rows = _normalize_candidates(
        candidates,
        allow_duplicate_assets=allow_duplicate_assets,
        sector_mode=_sector_eligibility_mode,
    )
    sources = {
        row["adjusted_close_source"]
        for row in candidate_rows.to_dict(orient="records")
        if _evaluation_exclusion(row, sector_mode=_sector_eligibility_mode) is None
    }
    if sources:
        normalized_bars, available_sources = _normalize_bars(bars)
        unavailable_sources = sorted(sources - available_sources)
        if unavailable_sources:
            raise ValueError(
                "bars does not provide " + ", ".join(unavailable_sources) + " adjusted close source"
            )
    else:
        normalized_bars = pd.DataFrame(
            columns=("asset_id", "trade_date", "adjusted_close_source", "adjusted_close")
        )
    market_regime = _snapshot_market_regime(snapshot)

    rows: list[dict[str, object]] = []
    for candidate in candidate_rows.to_dict(orient="records"):
        asset_id = candidate["asset_id"]
        anchor_close, anchor_status, anchor_error = _anchor_close(candidate.get("anchor_close"))
        source = candidate["adjusted_close_source"]
        future = normalized_bars.loc[
            normalized_bars["asset_id"].eq(asset_id)
            & normalized_bars["adjusted_close_source"].eq(source)
            & normalized_bars["trade_date"].gt(anchor)
            & normalized_bars["trade_date"].le(cutoff)
        ]
        for horizon in normalized_horizons:
            row = {
                "snapshot_id": snapshot_id,
                "anchor_date": anchor.isoformat(),
                "evaluation_cutoff": cutoff.isoformat(),
                "asset_id": asset_id,
                "sector_system": candidate["sector_system"],
                "sector_code": candidate["sector_code"],
                "sector_name": candidate["sector_name"],
                "sector_gate_status": candidate["sector_gate_status"],
                "sector_recovery_state": candidate["sector_recovery_state"],
                "market_regime": market_regime,
                "stock_lifecycle": candidate["stock_lifecycle"],
                "stock_rank": candidate["stock_rank"],
                "anchor_close": anchor_close,
                "adjusted_close_source": candidate["adjusted_close_source"],
                "forward_horizon_days": horizon,
                "forward_endpoint_date": pd.NA,
                "forward_endpoint_close": float("nan"),
                "forward_Nd_return": float("nan"),
                "forward_Nd_status": "pending",
                "hit_3pct": pd.NA,
                "hit_5pct": pd.NA,
                "hit_7pct": pd.NA,
                "evaluation_status": "pending",
                "data_status": anchor_status,
                "data_error": anchor_error,
            }
            if allow_duplicate_assets:
                row["sector_stock_rank"] = candidate.get("sector_stock_rank", pd.NA)
                row["sector_research_eligibility"] = candidate.get(
                    "sector_research_eligibility", pd.NA
                )
                row["target_trade_date"] = pd.NA
                row["endpoint_close"] = float("nan")
                row["status"] = "pending"
            exclusion = _evaluation_exclusion(
                candidate, sector_mode=_sector_eligibility_mode
            )
            if exclusion is not None:
                row["evaluation_status"] = exclusion
                row["data_status"] = exclusion
                row["data_error"] = ""
                if allow_duplicate_assets:
                    row["status"] = exclusion
                rows.append(row)
                continue
            if anchor_status != "ok":
                row["evaluation_status"] = "data_error"
                if allow_duplicate_assets:
                    row["status"] = "data_error"
                rows.append(row)
                continue
            if len(future) < horizon:
                row["data_status"] = "ok"
                if allow_duplicate_assets and not future.empty:
                    row["target_trade_date"] = future.iloc[-1]["trade_date"].isoformat()
                rows.append(row)
                continue
            endpoint = future.iloc[horizon - 1]
            endpoint_close = float(endpoint["adjusted_close"])
            forward_return = endpoint_close / anchor_close - 1.0
            row.update(
                {
                    "forward_endpoint_date": endpoint["trade_date"].isoformat(),
                    "forward_endpoint_close": endpoint_close,
                    "forward_Nd_return": forward_return,
                    "forward_Nd_status": "complete",
                    "hit_3pct": forward_return >= 0.03,
                    "hit_5pct": forward_return >= 0.05,
                    "hit_7pct": forward_return >= 0.07,
                    "evaluation_status": "complete",
                    "data_status": "ok",
                }
            )
            if allow_duplicate_assets:
                row.update(
                    {
                        "target_trade_date": endpoint["trade_date"].isoformat(),
                        "endpoint_close": endpoint_close,
                        "status": "complete",
                    }
                )
            rows.append(row)
    columns = _SECTOR_DETAIL_COLUMNS if allow_duplicate_assets else _DETAIL_COLUMNS
    return pd.DataFrame(rows, columns=columns)


def evaluate_sector_snapshot(
    snapshot: dict[str, object],
    *,
    bars: pd.DataFrame,
    evaluation_cutoff: date,
    horizons: Sequence[int] = (1, 3, 5),
) -> pd.DataFrame:
    """Evaluate a full-sector snapshot without collapsing shared assets.

    Batch snapshots intentionally allow an asset to occur in more than one
    sector.  The identity of an outcome is therefore the composite
    ``(asset_id, sector_system, sector_code, forward_horizon_days)`` rather
    than the asset alone.  Prices are still looked up once per asset/date;
    the same future bar may legitimately support multiple sector outcomes.

    ``target_trade_date``/``endpoint_close``/``status`` are stable, concise
    aliases for the existing ``forward_endpoint_date``/
    ``forward_endpoint_close``/``forward_Nd_status`` columns.  For a pending
    horizon with at least one observed future session, the target date is the
    latest observed session at the cutoff so that the pending boundary is
    auditable without pretending that the return is complete.
    """

    detail = evaluate_snapshot(
        snapshot,
        bars=bars,
        evaluation_cutoff=evaluation_cutoff,
        horizons=horizons,
        allow_duplicate_assets=True,
        _sector_eligibility_mode=True,
    )
    if detail.empty:
        return detail

    candidate_frame = snapshot.get("stock_candidates")
    if not isinstance(candidate_frame, pd.DataFrame):
        raise TypeError("snapshot stock_candidates must be a pandas DataFrame")
    candidate_rank: dict[tuple[str, str, str], object] = {}
    for row in candidate_frame.to_dict(orient="records"):
        key = _sector_identity(row.get("asset_id"), row.get("sector_system"), row.get("sector_code"))
        if key in candidate_rank:
            raise ValueError("snapshot stock_candidates contains duplicate asset/sector composite key")
        candidate_rank[key] = row.get("sector_rank", pd.NA)

    sector_states = snapshot.get("sector_states")
    if isinstance(sector_states, pd.DataFrame) and not sector_states.empty:
        for row in sector_states.to_dict(orient="records"):
            key = _sector_identity(None, row.get("sector_system"), row.get("sector_code"))
            value = row.get("sector_rank", pd.NA)
            for candidate_key in tuple(candidate_rank):
                if candidate_key[1:] == key[1:]:
                    if pd.isna(candidate_rank[candidate_key]) and pd.notna(value):
                        candidate_rank[candidate_key] = value

    detail = detail.copy(deep=True)
    detail["sector_rank"] = [
        candidate_rank.get(
            _sector_identity(asset_id, system, code),
            pd.NA,
        )
        for asset_id, system, code in zip(
            detail["asset_id"], detail["sector_system"], detail["sector_code"], strict=True
        )
    ]
    detail["sector_rank"] = pd.to_numeric(detail["sector_rank"], errors="coerce").astype("Int64")
    detail["target_trade_date"] = detail["target_trade_date"].astype("string")
    detail["status"] = detail["status"].astype("string")
    return detail.loc[:, _SECTOR_DETAIL_COLUMNS]


def summarize_sector_rolling_evaluation(detail: pd.DataFrame) -> pd.DataFrame:
    """Summarize batch outcomes by sector and both ranking dimensions.

    Unlike :func:`summarize_rolling_evaluation`, this function deliberately
    treats duplicate assets in different sectors as separate observations and
    groups on the sector-local ``sector_stock_rank`` field.
    """

    normalized = _normalize_sector_detail(detail)
    if normalized.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    normalized["_sector"] = [
        _sector_key(system, code)
        for system, code in zip(
            normalized["sector_system"], normalized["sector_code"], strict=True
        )
    ]
    normalized["_sector_rank_bucket"] = normalized["sector_rank"].map(_rank_bucket)
    normalized["_sector_stock_rank_bucket"] = normalized["sector_stock_rank"].map(_rank_bucket)
    groups: tuple[tuple[str, str | None], ...] = (
        ("overall", None),
        ("sector", "_sector"),
        ("sector_recovery_state", "sector_recovery_state"),
        ("sector_research_eligibility", "sector_research_eligibility"),
        ("sector_rank_bucket", "_sector_rank_bucket"),
        ("sector_stock_rank_bucket", "_sector_stock_rank_bucket"),
    )
    rows: list[dict[str, object]] = []
    for group_by, column in groups:
        if column is None:
            grouped = [("all", normalized)]
        else:
            values = normalized[column].fillna("unknown").astype(str)
            grouped = [
                (str(value), normalized.loc[values.eq(value)])
                for value in sorted(values.unique())
            ]
        for group_value, frame in grouped:
            for horizon, horizon_frame in frame.groupby("forward_horizon_days", sort=True):
                rows.append(_summarize_group(group_by, group_value, int(horizon), horizon_frame))
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS).sort_values(
        ["group_by", "group_value", "forward_horizon_days"], kind="mergesort"
    ).reset_index(drop=True)


def completed_outcomes_before_anchor(
    detail: pd.DataFrame, *, next_anchor: date
) -> pd.DataFrame:
    """Return immutable, complete outcomes available before ``next_anchor``.

    The helper is intentionally fail-closed: a mixed complete/pending frame,
    a target on/after the next anchor, or an evaluation cutoff after that
    anchor is rejected instead of silently allowing future information into
    calibration.
    """

    if not isinstance(detail, pd.DataFrame):
        raise TypeError("detail must be a pandas DataFrame")
    anchor = _normalize_date(next_anchor, "next_anchor")
    normalized = _normalize_sector_detail(detail)
    if normalized.empty:
        return normalized.copy(deep=True)
    row_anchor = _strict_date_series(normalized["anchor_date"], "anchor_date")
    cutoff = _strict_date_series(normalized["evaluation_cutoff"], "evaluation_cutoff")
    if (cutoff > anchor).any():
        raise ValueError("evaluation_cutoff must not follow next_anchor")
    target = _strict_date_series(normalized["target_trade_date"], "target_trade_date")
    status = normalized["status"].astype("string").fillna("").str.strip().str.casefold()
    evaluation_status = normalized["_evaluation_status"]
    data_status = (
        normalized["data_status"].astype("string").fillna("").str.strip().str.casefold()
    )
    if not evaluation_status.eq("complete").all():
        raise ValueError("evaluation_status must be complete")
    if not data_status.eq("ok").all():
        raise ValueError("data_status must be ok")
    complete = status.eq("complete") & normalized["forward_Nd_status"].astype("string").str.casefold().eq("complete")
    if not complete.all():
        raise ValueError("calibration outcomes must be complete")
    returns = pd.to_numeric(normalized["forward_Nd_return"], errors="coerce")
    finite_returns = returns.map(
        lambda value: isfinite(float(value)) if pd.notna(value) else False
    )
    if not finite_returns.all():
        raise ValueError("forward_Nd_return must be finite")
    for column in ("forward_endpoint_close", "endpoint_close"):
        endpoint = pd.to_numeric(normalized[column], errors="coerce")
        finite_endpoint = endpoint.map(
            lambda value: isfinite(float(value)) and float(value) > 0
            if pd.notna(value)
            else False
        )
        if not finite_endpoint.all():
            raise ValueError("endpoint_close must be finite and positive")
    if (target >= anchor).any():
        raise ValueError("target_trade_date must precede next_anchor")
    if (target <= row_anchor).any():
        raise ValueError("target_trade_date must follow anchor_date")
    result = normalized.loc[complete, list(_SECTOR_DETAIL_COLUMNS)].copy(deep=True).reset_index(drop=True)
    return result


def calibration_outcomes_before(
    detail: pd.DataFrame, next_anchor: date
) -> pd.DataFrame:
    """Compatibility alias for :func:`completed_outcomes_before_anchor`."""

    return completed_outcomes_before_anchor(detail, next_anchor=next_anchor)


def _sector_identity(asset_id: object, system: object, code: object) -> tuple[str, str, str]:
    def text(value: object) -> str:
        return "" if value is None or pd.isna(value) else str(value).strip()

    return text(asset_id), text(system), text(code)


def _normalize_sector_detail(detail: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(detail, pd.DataFrame):
        raise TypeError("detail must be a pandas DataFrame")
    if detail.empty:
        return pd.DataFrame(columns=_SECTOR_DETAIL_COLUMNS)
    normalized = detail.copy(deep=True)
    required = {"forward_horizon_days", "forward_Nd_return"}
    missing = required - set(normalized.columns)
    if missing:
        raise ValueError(f"detail is missing required columns: {', '.join(sorted(missing))}")
    if "forward_Nd_status" not in normalized:
        normalized["forward_Nd_status"] = normalized.get(
            "status", pd.Series("pending", index=normalized.index)
        )
    if "evaluation_status" not in normalized:
        normalized["evaluation_status"] = normalized.get(
            "status", normalized["forward_Nd_status"]
        )
    if "status" not in normalized:
        normalized["status"] = normalized["forward_Nd_status"]
    if "target_trade_date" not in normalized:
        normalized["target_trade_date"] = normalized.get(
            "forward_endpoint_date", pd.Series(pd.NA, index=normalized.index)
        )
    if "endpoint_close" not in normalized:
        normalized["endpoint_close"] = normalized.get(
            "forward_endpoint_close", pd.Series(float("nan"), index=normalized.index)
        )
    if "data_status" not in normalized:
        normalized["data_status"] = pd.NA
    for column in (
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_recovery_state",
        "sector_research_eligibility",
    ):
        if column not in normalized:
            normalized[column] = pd.NA
    if "sector_stock_rank" not in normalized:
        normalized["sector_stock_rank"] = pd.NA
    if "sector_rank" not in normalized:
        normalized["sector_rank"] = pd.NA
    normalized["forward_horizon_days"] = pd.to_numeric(
        normalized["forward_horizon_days"], errors="coerce"
    )
    if normalized["forward_horizon_days"].isna().any():
        raise ValueError("detail forward_horizon_days must be numeric")
    normalized["forward_Nd_return"] = pd.to_numeric(
        normalized["forward_Nd_return"], errors="coerce"
    )
    normalized["_evaluation_status"] = (
        normalized["evaluation_status"].astype("string").fillna("data_error").str.strip().str.casefold()
    )
    normalized["forward_Nd_status"] = (
        normalized["forward_Nd_status"].astype("string").fillna("pending").str.strip().str.casefold()
    )
    normalized["status"] = normalized["status"].astype("string").fillna("pending").str.strip().str.casefold()
    normalized["sector_recovery_state"] = normalized["sector_recovery_state"].astype("string").str.strip().replace("", pd.NA)
    normalized["sector_research_eligibility"] = normalized["sector_research_eligibility"].astype("string").str.strip().replace("", pd.NA)
    normalized["sector_stock_rank"] = pd.to_numeric(normalized["sector_stock_rank"], errors="coerce")
    normalized["sector_rank"] = pd.to_numeric(normalized["sector_rank"], errors="coerce")
    return normalized


def _strict_date_series(values: pd.Series, field_name: str) -> pd.Series:
    result: list[date] = []
    for value in values:
        if value is None or pd.isna(value):
            raise ValueError(f"{field_name} must contain dates")
        result.append(_normalize_date(value, field_name))
    return pd.Series(result, index=values.index, dtype="object")


def summarize_rolling_evaluation(detail: pd.DataFrame) -> pd.DataFrame:
    """Return hit rates, return distributions, and sector/state conditional summaries."""

    if not isinstance(detail, pd.DataFrame):
        raise TypeError("detail must be a pandas DataFrame")
    missing = {"forward_horizon_days", "forward_Nd_status", "forward_Nd_return"} - set(detail.columns)
    if missing and not detail.empty:
        raise ValueError(f"detail is missing required columns: {', '.join(sorted(missing))}")
    if detail.empty:
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)

    normalized = detail.copy(deep=True)
    normalized["forward_horizon_days"] = pd.to_numeric(
        normalized["forward_horizon_days"], errors="coerce"
    )
    if normalized["forward_horizon_days"].isna().any():
        raise ValueError("detail forward_horizon_days must be numeric")
    normalized["forward_Nd_return"] = pd.to_numeric(
        normalized["forward_Nd_return"], errors="coerce"
    )
    evaluation_status = normalized.get("evaluation_status")
    if evaluation_status is None:
        raw_data_status = normalized.get(
            "data_status", pd.Series("ok", index=normalized.index, dtype="string")
        )
        raw_data_status = raw_data_status.astype("string").fillna("").str.strip().str.casefold()
        excluded = raw_data_status.str.startswith("excluded_")
        data_error = ~raw_data_status.isin(("", "ok")) & ~excluded
        evaluation_status = pd.Series("pending", index=normalized.index, dtype="string")
        evaluation_status.loc[normalized["forward_Nd_status"].eq("complete") & ~data_error & ~excluded] = "complete"
        evaluation_status.loc[data_error] = "data_error"
        evaluation_status.loc[excluded] = raw_data_status.loc[excluded]
    normalized["_evaluation_status"] = evaluation_status.astype("string").fillna("data_error")
    normalized["_rank_bucket"] = normalized.get(
        "stock_rank", pd.Series(pd.NA, index=normalized.index)
    ).map(_rank_bucket)
    normalized["_sector"] = [
        _sector_key(system, code)
        for system, code in zip(
            normalized.get("sector_system", pd.Series(pd.NA, index=normalized.index)),
            normalized.get("sector_code", pd.Series(pd.NA, index=normalized.index)),
            strict=True,
        )
    ]
    groups: tuple[tuple[str, str | None], ...] = (
        ("overall", None),
        ("sector", "_sector"),
        ("market_regime", "market_regime"),
        ("sector_recovery_state", "sector_recovery_state"),
        ("stock_lifecycle", "stock_lifecycle"),
        ("rank_bucket", "_rank_bucket"),
    )
    rows: list[dict[str, object]] = []
    for group_by, column in groups:
        if column is None:
            grouped = [("all", normalized)]
        else:
            values = normalized.get(column, pd.Series("unknown", index=normalized.index))
            values = values.fillna("unknown").astype(str)
            grouped = [
                (str(value), normalized.loc[values.eq(value)])
                for value in sorted(values.unique())
            ]
        for group_value, frame in grouped:
            for horizon, horizon_frame in frame.groupby("forward_horizon_days", sort=True):
                rows.append(_summarize_group(group_by, group_value, int(horizon), horizon_frame))
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS).sort_values(
        ["group_by", "group_value", "forward_horizon_days"], kind="mergesort"
    ).reset_index(drop=True)


def _normalize_horizons(horizons: Sequence[int]) -> tuple[int, ...]:
    if not isinstance(horizons, Sequence) or isinstance(horizons, (str, bytes)) or not horizons:
        raise ValueError("horizons must be a non-empty sequence of positive integers")
    if any(type(value) is not int or value <= 0 for value in horizons):
        raise ValueError("horizons must contain positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must contain unique values")
    return tuple(sorted(horizons))


def _normalize_candidates(
    candidates: pd.DataFrame,
    *,
    allow_duplicate_assets: bool = False,
    sector_mode: bool = False,
) -> pd.DataFrame:
    required = {"asset_id", "anchor_close"}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"snapshot stock_candidates is missing columns: {', '.join(sorted(missing))}")
    result = candidates.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    if result["asset_id"].isna().any() or result["asset_id"].eq("").any():
        raise ValueError("snapshot stock_candidates asset_id must be non-empty")
    if not allow_duplicate_assets and result["asset_id"].duplicated().any():
        raise ValueError("snapshot stock_candidates contains duplicate asset_id values")
    for column in _CONTEXT_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    if allow_duplicate_assets:
        if result.duplicated(["asset_id", "sector_system", "sector_code"]).any():
            raise ValueError(
                "snapshot stock_candidates contains duplicate asset/sector composite key"
            )
        if "sector_stock_rank" not in result:
            result["sector_stock_rank"] = pd.NA
    if "adjusted_close_source" not in result:
        result["adjusted_close_source"] = pd.NA
    result["adjusted_close_source"] = result["adjusted_close_source"].astype("string").str.strip().replace("", pd.NA)
    excluded = result.apply(
        lambda row: _evaluation_exclusion(row.to_dict(), sector_mode=sector_mode) is not None,
        axis=1,
    )
    invalid_source = (
        result["adjusted_close_source"].isna() | ~result["adjusted_close_source"].isin(_PRICE_SOURCES)
    ) & ~excluded
    if invalid_source.any():
        raise ValueError("snapshot adjusted_close_source must be one of raw, qfq, hfq")
    return result


def _normalize_bars(bars: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("bars must be a pandas DataFrame")
    required = {"asset_id", "trade_date"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"bars is missing columns: {', '.join(sorted(missing))}")
    identity = bars.loc[:, ["asset_id", "trade_date"]].copy(deep=True)
    identity["asset_id"] = identity["asset_id"].astype("string").str.strip()
    if identity["asset_id"].isna().any() or identity["asset_id"].eq("").any():
        raise ValueError("bars asset_id must be non-empty")
    identity["trade_date"] = identity["trade_date"].map(
        lambda value: _normalize_date(value, "bars trade_date")
    )
    source_column = _bar_source_column(bars)
    frames: list[pd.DataFrame] = []
    available_sources: set[str] = set()
    for source, columns in _PRICE_SOURCE_COLUMNS.items():
        present = [column for column in columns if column in bars]
        if len(present) > 1:
            raise ValueError(f"bars has ambiguous {source} adjusted close columns")
        if present:
            frames.append(_bar_price_frame(identity, bars[present[0]], source))
            available_sources.add(source)
    generic_column = next(
        (column for column in ("adjusted_close", "adj_close", "close") if column in bars), None
    )
    if generic_column is not None:
        if source_column is None:
            if generic_column != "close":
                raise ValueError("generic adjusted close bars must include adjusted_close_source or adjust_type")
            frames.append(_bar_price_frame(identity, bars[generic_column], "raw"))
            available_sources.add("raw")
        else:
            source_values = bars[source_column].astype("string").str.strip().replace("", pd.NA)
            invalid_source = source_values.isna() | ~source_values.isin(_PRICE_SOURCES)
            if invalid_source.any():
                raise ValueError("bars adjusted_close_source must be one of raw, qfq, hfq")
            for source in sorted(source_values.unique()):
                frames.append(
                    _bar_price_frame(identity.loc[source_values.eq(source)], bars.loc[source_values.eq(source), generic_column], source)
                )
                available_sources.add(source)
    if not frames:
        raise ValueError("bars is missing a source-specific or source-labelled adjusted close column")
    result = pd.concat(frames, ignore_index=True)
    if result.duplicated(["asset_id", "trade_date", "adjusted_close_source"]).any():
        raise ValueError("bars contains duplicate bar rows for asset_id, trade_date, and adjusted close source")
    result["adjusted_close"] = pd.to_numeric(result["adjusted_close"], errors="coerce")
    finite_close = result["adjusted_close"].map(
        lambda value: isfinite(float(value)) if pd.notna(value) else False
    )
    if result["adjusted_close"].isna().any() or not finite_close.all() or (result["adjusted_close"] <= 0).any():
        raise ValueError("bars adjusted close must contain finite positive numbers")
    return (
        result.sort_values(["asset_id", "adjusted_close_source", "trade_date"], kind="mergesort").reset_index(drop=True),
        available_sources,
    )


def _bar_source_column(bars: pd.DataFrame) -> str | None:
    columns = [column for column in ("adjusted_close_source", "adjust_type") if column in bars]
    if len(columns) == 2:
        left = bars[columns[0]].astype("string").str.strip().replace("", pd.NA)
        right = bars[columns[1]].astype("string").str.strip().replace("", pd.NA)
        if not left.equals(right):
            raise ValueError("bars adjusted_close_source and adjust_type conflict")
    return columns[0] if columns else None


def _bar_price_frame(identity: pd.DataFrame, close: pd.Series, source: str) -> pd.DataFrame:
    result = identity.copy(deep=True)
    result["adjusted_close"] = close.to_numpy(copy=True)
    result["adjusted_close_source"] = source
    return result


def _snapshot_market_regime(snapshot: dict[str, object]) -> str:
    value = snapshot.get("market_regime", "unknown")
    if isinstance(value, dict):
        value = value.get("market_regime", "unknown")
    text = str(value).strip() if value is not None else ""
    return text or "unknown"


def _normalize_date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO date") from error
    raise ValueError(f"{field_name} must be a date")


def _require_nonempty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _anchor_close(value: object) -> tuple[float, str, str]:
    if value is None or pd.isna(value):
        return float("nan"), "missing_anchor_close", "snapshot anchor_close is missing"
    if isinstance(value, bool) or not isinstance(value, Real):
        return float("nan"), "invalid_anchor_close", "snapshot anchor_close must be a finite positive number"
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        return float("nan"), "invalid_anchor_close", "snapshot anchor_close must be a finite positive number"
    return normalized, "ok", ""


def _evaluation_exclusion(
    candidate: dict[str, object], *, sector_mode: bool = False
) -> str | None:
    # Preserve the legacy evaluator's precedence for rows carrying both
    # statuses.  Sector mode intentionally bypasses this legacy gate below so
    # a research-visible sector is not discarded merely because the old gate
    # is blocked.
    if not sector_mode and str(candidate["sector_gate_status"]).strip().lower() == "blocked":
        return "excluded_blocked"
    if str(candidate["stock_lifecycle"]).strip().lower() == "invalidated":
        return "excluded_invalidated"
    if sector_mode:
        raw_eligibility = candidate.get("sector_research_eligibility")
        has_eligibility = raw_eligibility is not None and not pd.isna(raw_eligibility)
        if has_eligibility:
            eligibility = str(raw_eligibility).strip().casefold()
            if eligibility in {"eligible", "watch"}:
                return None
            if eligibility == "blocked_data":
                return "excluded_blocked_data"
            return "excluded_sector_ineligible"
    if str(candidate["sector_gate_status"]).strip().lower() == "blocked":
        return "excluded_blocked"
    return None


def _rank_bucket(value: object) -> str:
    rank = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(rank) or rank <= 0 or rank % 1:
        return "unranked"
    if rank == 1:
        return "top_1"
    if rank <= 5:
        return "top_2_5"
    if rank <= 10:
        return "top_6_10"
    return "top_11_plus"


def _sector_key(system: object, code: object) -> str:
    left = str(system).strip() if pd.notna(system) else "unknown"
    right = str(code).strip() if pd.notna(code) else "unknown"
    return f"{left or 'unknown'}:{right or 'unknown'}"


def _summarize_group(
    group_by: str, group_value: str, horizon: int, frame: pd.DataFrame
) -> dict[str, object]:
    excluded = frame["_evaluation_status"].str.startswith("excluded_")
    data_error = frame["_evaluation_status"].eq("data_error")
    complete = (
        frame["_evaluation_status"].eq("complete")
        & frame["forward_Nd_status"].eq("complete")
        & frame["forward_Nd_return"].notna()
    )
    finite_return = frame["forward_Nd_return"].map(
        lambda value: isfinite(float(value)) if pd.notna(value) else False
    )
    returns = frame.loc[complete & finite_return, "forward_Nd_return"]
    total_count = int(len(frame))
    complete_count = int(len(returns))
    excluded_count = int(excluded.sum())
    error_count = int(data_error.sum())
    pending_count = total_count - complete_count - excluded_count - error_count
    if returns.empty:
        metrics: dict[str, object] = {name: float("nan") for name in _SUMMARY_COLUMNS[8:]}
    else:
        metrics = {
            "up_ratio": float((returns > 0).mean()),
            "mean_return": float(returns.mean()),
            "median_return": float(returns.median()),
            "p25_return": float(returns.quantile(0.25)),
            "p75_return": float(returns.quantile(0.75)),
            "p90_return": float(returns.quantile(0.90)),
            "hit_3pct_rate": float((returns >= 0.03).mean()),
            "hit_5pct_rate": float((returns >= 0.05).mean()),
            "hit_7pct_rate": float((returns >= 0.07).mean()),
        }
    return {
        "group_by": group_by,
        "group_value": group_value,
        "forward_horizon_days": horizon,
        "total_count": total_count,
        "complete_count": complete_count,
        "pending_count": pending_count,
        "excluded_count": excluded_count,
        "data_error_count": error_count,
        **metrics,
    }
