"""Deterministic stock ranking within rolling oversold sector states.

This stage intentionally consumes only supplied data frames.  The optional
consumer-V2 adapter calls calculation helpers over in-memory frames and never
loads data or contacts a network source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from stock_research.strategy_data_policy import DataGap

from .contracts import GateStatus, RecoveryState, RollingOversoldConfig, StockLifecycle


_KEY_COLUMNS = ("sector_system", "sector_code")
_SECTOR_CONTEXT_COLUMNS = (
    "sector_system",
    "sector_code",
    "sector_name",
    "sector_oversold_score",
    "sector_repairability_score",
    "sector_direction_score",
    "sector_recovery_state",
    "sector_gate_status",
)
_COMPONENT_COLUMNS = (
    "stock_oversold_depth_score",
    "stock_residual_distance_score",
    "stock_excess_return_score",
    "sector_oversold_component",
    "sector_repairability_component",
    "sector_direction_component",
    "stock_activity_score",
    "stock_quality_score",
    "stock_valuation_score",
    "stock_size_elasticity_score",
)
_OUTPUT_COLUMNS = (
    "snapshot_id",
    "anchor_date",
    "data_cutoff_date",
    "score_version",
    "market_regime",
    "previous_snapshot_id",
    "rank_delta",
    "lifecycle_delta",
    *_SECTOR_CONTEXT_COLUMNS,
    "asset_id",
    "stock_feature_source",
    "anchor_return",
    "distance_to_252d_high",
    "oversold_depth",
    "stock_excess_return",
    *_COMPONENT_COLUMNS,
    "stock_score",
    "stock_rank",
    "stock_lifecycle",
    "score_status",
    "score_reason",
)
_SECTOR_KEY_ALIASES = (
    ("industry_system", "industry_code", "industry_name"),
    ("concept_system", "concept_code", "concept_name"),
)


class StockScoringDataGap(ValueError):
    """A fail-closed stock scoring error with structured missing-data detail."""

    def __init__(self, gap: DataGap) -> None:
        self.gap = gap
        super().__init__(
            f"stock scoring data gap {gap.dataset} asset {gap.asset_id}: {gap.reason}"
        )


def classify_stock_lifecycle(
    *,
    anchor_return: float,
    distance_to_252d_high: float,
    sector_recovery_state: str,
    sector_gate_status: str,
    repair_trigger_return: float,
    residual_high_distance: float,
) -> str:
    """Classify stock repair progress without discarding residual upside."""

    if str(sector_gate_status).strip() == GateStatus.BLOCKED.value:
        return StockLifecycle.INVALIDATED.value
    if (
        anchor_return >= repair_trigger_return
        and distance_to_252d_high >= residual_high_distance
        and str(sector_recovery_state).strip()
        in {RecoveryState.FRESH_OVERSOLD.value, RecoveryState.REPAIRING.value}
    ):
        return StockLifecycle.REPAIR_WITH_RESIDUAL_SPACE.value
    if anchor_return >= repair_trigger_return:
        return StockLifecycle.CONFIRMED_REPAIR.value
    if str(sector_recovery_state).strip() == RecoveryState.FRESH_OVERSOLD.value:
        return StockLifecycle.NEW_OVERSOLD.value
    return StockLifecycle.EXPECTED_REPAIR.value


def score_rolling_stock_candidates(
    stock_features: pd.DataFrame,
    sector_states: pd.DataFrame,
    *,
    top_n: int,
    config: RollingOversoldConfig,
) -> pd.DataFrame:
    """Return fresh, explainable stock candidates from non-blocked sector states.

    Missing sector context and incomplete score inputs fail closed.  In
    particular, this function never fills a required score component with zero.
    """

    if not isinstance(stock_features, pd.DataFrame) or not isinstance(sector_states, pd.DataFrame):
        raise TypeError("stock_features and sector_states must be pandas DataFrames")
    if type(top_n) is not int or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")
    if stock_features.empty:
        return _empty_result()

    stocks = _canonicalize_stock(_adapt_consumer_v2_features(stock_features, config))
    # Stock-side sector fields only establish an input mapping.  The matched
    # sector-state row is authoritative for all canonical context/output fields,
    # leaving one unambiguous column for each field at merge time.
    stocks = stocks.drop(
        columns=[
            *[column for column in _SECTOR_CONTEXT_COLUMNS if column not in _KEY_COLUMNS],
            "market_regime",
        ],
        errors="ignore",
    )
    sectors = _canonicalize_sector(sector_states)
    _require_stock_sector_keys(stocks)
    _require_sector_context(stocks, sectors, config)
    sector_context = sectors.loc[:, list(_SECTOR_CONTEXT_COLUMNS)].copy()
    sector_context["market_regime"] = (
        sectors["market_regime"] if "market_regime" in sectors else "unknown"
    )
    sector_context["_sector_context_matched"] = True
    joined = stocks.merge(
        sector_context,
        on=list(_KEY_COLUMNS),
        how="left",
        validate="many_to_one",
        sort=False,
    )
    _raise_missing_sector_context(joined, config)
    _validate_matched_sector_context(joined)
    joined["market_regime"] = (
        joined["market_regime"].astype("string").str.strip().replace("", pd.NA).fillna("unknown")
    )

    blocked = joined["sector_gate_status"].eq(GateStatus.BLOCKED.value)
    active = joined.loc[~blocked].copy()
    if active.empty:
        return _empty_result()

    _assign_required_features(active)
    _validate_sector_numeric_context(active)
    _score_components(active)
    active["stock_lifecycle"] = [
        classify_stock_lifecycle(
            anchor_return=anchor_return,
            distance_to_252d_high=distance,
            sector_recovery_state=state,
            sector_gate_status=gate,
            repair_trigger_return=config.repair_trigger_return,
            residual_high_distance=config.residual_high_distance,
        )
        for anchor_return, distance, state, gate in zip(
            active["anchor_return"],
            active["distance_to_252d_high"],
            active["sector_recovery_state"],
            active["sector_gate_status"],
            strict=True,
        )
    ]
    active["score_status"] = "scored"
    active["score_reason"] = ""
    active["stock_feature_source"] = active.get(
        "stock_feature_source", pd.Series("precomputed", index=active.index)
    ).fillna("precomputed")
    _assign_revision_identity(active, config)

    # Confirmed repairs are useful evaluation context, not fresh entries.
    # State classification above deliberately remains authoritative: a
    # non-blocked expected_repair row is still a valid candidate.
    selected = active.loc[
        ~active["stock_lifecycle"].eq(StockLifecycle.CONFIRMED_REPAIR.value)
    ].copy()
    selected = selected.sort_values(
        ["stock_score", "asset_id", "sector_system", "sector_code"],
        ascending=[False, True, True, True],
        kind="mergesort",
    ).head(top_n)
    selected["stock_rank"] = np.arange(1, len(selected) + 1, dtype=int)
    return _output_frame(selected)


def _adapt_consumer_v2_features(
    stock_features: pd.DataFrame, config: RollingOversoldConfig
) -> pd.DataFrame:
    """Enrich compatible in-memory consumer-V2 inputs without any data loading."""

    result = stock_features.copy(deep=True)
    result.attrs = dict(stock_features.attrs)
    sources = result.attrs.get("consumer_v2_inputs")
    if "asset_id" in result:
        result["asset_id"] = result["asset_id"].astype("string").str.strip()
    # A bar panel with a consumer classification can use the existing V2 price
    # calculator directly.  It is deliberately an adapter, not a parallel
    # implementation of that point-in-time feature logic.
    if {"asset_id", "trade_date", "close", "consumer_subindustry"}.issubset(result.columns):
        from stock_research.consumer_oversold.features import compute_price_features

        membership = _deduplicate_consumer_membership(result)
        price = compute_price_features(
            result.loc[:, ["asset_id", "trade_date", "close"]],
            membership,
            trade_date=config.anchor_start_date.isoformat(),
        )
        result = _merge_feature_columns(result, price)
        _fill_missing_from(result, "anchor_return", "return_60d")
        _fill_missing_from(result, "distance_to_252d_high", "max_drawdown_12m", negate=True)
        _fill_missing_from(result, "oversold_depth", "max_drawdown_12m", negate=True)
        _fill_missing_from(result, "stock_excess_return", "relative_return_60d")
        result["stock_feature_source"] = "consumer_v2_price"

    # Finance panels can likewise use the V2 point-in-time fundamentals and
    # hard-risk helpers.  These helpers are pure DataFrame transforms.
    from stock_research.consumer_oversold.features import (
        FINANCE_COLUMNS,
        HARD_RISK_FUNDAMENTAL_COLUMNS,
        compute_fundamental_features,
        compute_hard_risk_features,
    )

    if set(FINANCE_COLUMNS).issubset(result.columns):
        fundamentals = compute_fundamental_features(
            result.loc[:, list(FINANCE_COLUMNS)], trade_date=config.anchor_start_date.isoformat()
        )
        result = _merge_feature_columns(result, fundamentals)
        _fill_missing_from(result, "quality", "latest_roe")
        result["stock_feature_source"] = "consumer_v2_fundamental"
    if set(HARD_RISK_FUNDAMENTAL_COLUMNS).issubset(result.columns):
        risk = compute_hard_risk_features(result.loc[:, list(HARD_RISK_FUNDAMENTAL_COLUMNS)])
        result = _merge_feature_columns(result, risk)

    # Call the V2 valuation helper when callers explicitly supply its three
    # compatible in-memory source frames through DataFrame attrs.  This avoids
    # inventing a second transport format for history while keeping this public
    # stage DB/network independent.
    if isinstance(sources, Mapping) and {
        "current_valuation", "valuation_history", "fundamentals"
    }.issubset(sources):
        from stock_research.consumer_oversold.features import compute_valuation_features

        valuation = compute_valuation_features(
            sources["current_valuation"], sources["valuation_history"], sources["fundamentals"]
        )
        result = _merge_feature_columns(result, valuation)
        _fill_missing_from(result, "valuation", "valuation_depression_percentile", scale=100.0)
        result["stock_feature_source"] = "consumer_v2_valuation"
    return result


def _deduplicate_consumer_membership(frame: pd.DataFrame) -> pd.DataFrame:
    membership = frame.loc[:, ["asset_id", "consumer_subindustry"]].copy()
    membership["asset_id"] = membership["asset_id"].astype("string").str.strip()
    membership["consumer_subindustry"] = membership["consumer_subindustry"].astype("string").str.strip()
    return membership.sort_values(["asset_id", "consumer_subindustry"], kind="mergesort").drop_duplicates(
        "asset_id", keep="last"
    )


def _merge_feature_columns(base: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return base
    additions = [column for column in features.columns if column != "asset_id" and column not in base]
    if not additions:
        return base
    return base.merge(features.loc[:, ["asset_id", *additions]], on="asset_id", how="left", sort=False)


def _fill_missing_from(
    frame: pd.DataFrame, target: str, source: str, *, negate: bool = False, scale: float = 1.0
) -> None:
    if source not in frame:
        return
    values = pd.to_numeric(frame[source], errors="coerce") * scale
    if negate:
        values = -values
    if target not in frame:
        frame[target] = values
    else:
        frame[target] = pd.to_numeric(frame[target], errors="coerce").fillna(values)


def _canonicalize_stock(frame: pd.DataFrame) -> pd.DataFrame:
    result = _canonicalize_sector_keys(frame)
    if "asset_id" not in result:
        raise ValueError("stock_features missing required column asset_id")
    result["asset_id"] = result["asset_id"].astype("string").str.strip().replace("", pd.NA)
    if result["asset_id"].isna().any():
        raise ValueError("stock_features asset_id must be non-empty")
    return _deterministically_deduplicate(result, ["asset_id", *_KEY_COLUMNS])


def _canonicalize_sector(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_SECTOR_CONTEXT_COLUMNS)
    result = _canonicalize_sector_keys(frame)
    missing = [column for column in _SECTOR_CONTEXT_COLUMNS if column not in result]
    if missing:
        raise ValueError(f"sector_states missing required columns: {', '.join(missing)}")
    result = _deterministically_deduplicate(result, list(_KEY_COLUMNS))
    for column in ("sector_recovery_state", "sector_gate_status"):
        result[column] = result[column].astype("string").str.strip().replace("", pd.NA)
    output_columns = [* _SECTOR_CONTEXT_COLUMNS]
    if "market_regime" in result:
        output_columns.append("market_regime")
    return result.loc[:, output_columns]


def _canonicalize_sector_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    for canonical, position in zip(("sector_system", "sector_code", "sector_name"), range(3), strict=True):
        candidates = [aliases[position] for aliases in _SECTOR_KEY_ALIASES if aliases[position] in result]
        fallback = (
            result.loc[:, candidates].bfill(axis=1).iloc[:, 0]
            if candidates
            else pd.Series(pd.NA, index=result.index, dtype="string")
        )
        current = result.get(canonical, pd.Series(pd.NA, index=result.index, dtype="string"))
        normalized = current.astype("string").str.strip().replace("", pd.NA)
        result[canonical] = normalized.fillna(fallback.astype("string").str.strip().replace("", pd.NA))
    return result


def _deterministically_deduplicate(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    result = frame.copy()
    # Use the complete normalized row as a deterministic tie breaker, so the
    # selected duplicate does not depend on source frame order.
    signature_columns = sorted(column for column in result.columns if column != "_duplicate_signature")
    result["_duplicate_signature"] = result.loc[:, signature_columns].apply(
        lambda row: "\x1f".join(_stable_scalar(value) for value in row), axis=1
    )
    result = result.sort_values([*keys, "_duplicate_signature"], kind="mergesort", na_position="first")
    return result.drop_duplicates(list(keys), keep="last").drop(columns="_duplicate_signature").reset_index(drop=True)


def _stable_scalar(value: object) -> str:
    return "<NA>" if bool(pd.isna(value)) else repr(value)


def _require_stock_sector_keys(stocks: pd.DataFrame) -> None:
    missing = stocks.loc[:, list(_KEY_COLUMNS)].isna().any(axis=1)
    if missing.any():
        row = stocks.loc[missing, ["asset_id", *_KEY_COLUMNS]].sort_values("asset_id", kind="mergesort").iloc[0]
        raise ValueError(
            f"stock_features asset {row['asset_id']} missing sector key "
            f"{row['sector_system']}/{row['sector_code']}"
        )


def _require_sector_context(
    stocks: pd.DataFrame, sectors: pd.DataFrame, config: RollingOversoldConfig
) -> None:
    if sectors.empty:
        row = stocks.sort_values("asset_id", kind="mergesort").iloc[0]
        _raise_sector_context_gap(row, config)


def _raise_missing_sector_context(
    joined: pd.DataFrame, config: RollingOversoldConfig
) -> None:
    missing = joined["_sector_context_matched"].isna()
    if missing.any():
        row = joined.loc[missing, ["asset_id", *_KEY_COLUMNS]].sort_values(
            ["asset_id", *_KEY_COLUMNS], kind="mergesort"
        ).iloc[0]
        _raise_sector_context_gap(row, config)


def _raise_sector_context_gap(row: pd.Series, config: RollingOversoldConfig) -> None:
    start_date = config.anchor_start_date.isoformat()
    end_date = (config.anchor_end_date or config.anchor_start_date).isoformat()
    key = f"{row['sector_system']}/{row['sector_code']}"
    gap = DataGap(
        dataset="sector_context",
        asset_id=str(row["asset_id"]),
        start_date=start_date,
        end_date=end_date,
        expected_rows=1,
        actual_rows=0,
        reason=f"missing_sector_context:{key}",
    )
    raise StockScoringDataGap(gap)


def _validate_matched_sector_context(joined: pd.DataFrame) -> None:
    """Reject incomplete matched rows before gate/lifecycle evaluation."""

    text_columns = (
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_recovery_state",
        "sector_gate_status",
    )
    numeric_columns = (
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
    )
    for column in text_columns:
        values = joined[column].astype("string").str.strip()
        invalid = values.isna() | values.eq("")
        if invalid.any():
            _raise_incomplete_sector_context(joined, invalid, column)
        joined[column] = values
    for column in numeric_columns:
        values = pd.to_numeric(joined[column], errors="coerce")
        invalid = values.isna() | ~np.isfinite(values)
        if invalid.any():
            _raise_incomplete_sector_context(joined, invalid, column)
        joined[column] = values.clip(0.0, 100.0)


def _raise_incomplete_sector_context(
    joined: pd.DataFrame, invalid: pd.Series, column: str
) -> None:
    row = joined.loc[invalid, ["asset_id", *_KEY_COLUMNS]].sort_values(
        ["asset_id", *_KEY_COLUMNS], kind="mergesort"
    ).iloc[0]
    raise ValueError(
        f"sector context for asset {row['asset_id']} key "
        f"{row['sector_system']}/{row['sector_code']} missing required field {column}"
    )


def _assign_required_features(frame: pd.DataFrame) -> None:
    values = {
        "anchor_return": _numeric_feature(frame, ("anchor_return", "rebound_from_low_60d", "return_60d")),
        "distance_to_252d_high": _distance_to_high(frame),
        "oversold_depth": _oversold_depth(frame),
        "stock_excess_return": _excess_return(frame),
        "_activity_input": _numeric_feature(
            frame, ("activity", "activity_score", "turnover_or_activity_score", "average_amount_20d")
        ),
        "_quality_input": _numeric_feature(
            frame, ("quality", "quality_score", "fundamental_quality_score", "latest_roe")
        ),
        "_valuation_input": _numeric_feature(
            frame, ("valuation", "valuation_score", "valuation_support_score", "valuation_depression_percentile")
        ),
        "_size_input": _numeric_feature(
            frame, ("size_elasticity", "size_elasticity_score", "current_float_market_cap", "market_cap")
        ),
    }
    for name, value in values.items():
        invalid = value.isna() | ~np.isfinite(value)
        if invalid.any():
            asset_id = frame.loc[invalid, "asset_id"].sort_values(kind="mergesort").iloc[0]
            raise ValueError(f"stock_features asset {asset_id} missing required feature {name.lstrip('_')}")
        frame[name] = value.astype(float)
    # Percentile inputs from consumer V2 are 0--1; generic scores remain 0--100.
    if "valuation_depression_percentile" in frame and "valuation" not in frame:
        frame["_valuation_input"] *= 100.0


def _numeric_feature(frame: pd.DataFrame, candidates: Sequence[str]) -> pd.Series:
    available = [column for column in candidates if column in frame]
    if not available:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    numeric = pd.DataFrame(
        {column: pd.to_numeric(frame[column], errors="coerce") for column in available}, index=frame.index
    )
    return numeric.bfill(axis=1).iloc[:, 0]


def _distance_to_high(frame: pd.DataFrame) -> pd.Series:
    direct = _numeric_feature(
        frame, ("distance_to_252d_high", "residual_distance_to_252d_high", "distance_to_high_252d")
    )
    if direct.notna().any():
        return direct
    return -_numeric_feature(frame, ("drawdown_from_high_1y", "max_drawdown_12m", "drawdown_252d"))


def _oversold_depth(frame: pd.DataFrame) -> pd.Series:
    direct = _numeric_feature(frame, ("oversold_depth",))
    if direct.notna().any():
        return direct.abs()
    return -_numeric_feature(frame, ("max_drawdown_12m", "drawdown_from_high_1y", "drawdown_252d"))


def _excess_return(frame: pd.DataFrame) -> pd.Series:
    direct = _numeric_feature(
        frame, ("stock_excess_return", "relative_return_20d", "relative_return_60d", "relative_return_6m")
    )
    if direct.notna().any():
        return direct
    stock_return = _numeric_feature(frame, ("stock_return", "return_20d", "return_60d", "return_6m"))
    sector_return = _numeric_feature(frame, ("sector_return", "sector_ret_20d", "sector_return_20d"))
    return stock_return - sector_return


def _validate_sector_numeric_context(frame: pd.DataFrame) -> None:
    for column in (
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
    ):
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.isna() | ~np.isfinite(values)
        if invalid.any():
            asset_id = frame.loc[invalid, "asset_id"].sort_values(kind="mergesort").iloc[0]
            raise ValueError(f"sector context for asset {asset_id} missing required feature {column}")
        frame[column] = values.clip(0.0, 100.0)


def _score_components(frame: pd.DataFrame) -> None:
    frame["stock_oversold_depth_score"] = (frame["oversold_depth"] / 0.30 * 100.0).clip(0.0, 100.0)
    frame["stock_residual_distance_score"] = (
        frame["distance_to_252d_high"] / 0.40 * 100.0
    ).clip(0.0, 100.0)
    frame["stock_excess_return_score"] = (
        50.0 + frame["stock_excess_return"] / 0.20 * 50.0
    ).clip(0.0, 100.0)
    frame["sector_oversold_component"] = frame["sector_oversold_score"]
    frame["sector_repairability_component"] = frame["sector_repairability_score"]
    frame["sector_direction_component"] = frame["sector_direction_score"]
    frame["stock_activity_score"] = _clipped_percentile(frame["_activity_input"], ascending=True)
    frame["stock_quality_score"] = frame["_quality_input"].clip(0.0, 100.0)
    frame["stock_valuation_score"] = frame["_valuation_input"].clip(0.0, 100.0)
    # Lower market-capacity inputs have more residual price elasticity.
    frame["stock_size_elasticity_score"] = _clipped_percentile(frame["_size_input"], ascending=False)
    frame["stock_score"] = sum(
        frame[column] * weight
        for column, weight in (
            ("stock_oversold_depth_score", 0.18),
            ("stock_residual_distance_score", 0.12),
            ("stock_excess_return_score", 0.10),
            ("sector_oversold_component", 0.10),
            ("sector_repairability_component", 0.12),
            ("sector_direction_component", 0.10),
            ("stock_activity_score", 0.10),
            ("stock_quality_score", 0.08),
            ("stock_valuation_score", 0.06),
            ("stock_size_elasticity_score", 0.04),
        )
    ).clip(0.0, 100.0)


def _clipped_percentile(values: pd.Series, *, ascending: bool) -> pd.Series:
    lower, upper = values.quantile([0.05, 0.95])
    clipped = values.clip(lower, upper)
    if len(clipped) == 1 or clipped.nunique(dropna=True) == 1:
        return pd.Series(50.0, index=values.index, dtype="float64")
    ranks = clipped.rank(method="average", ascending=ascending)
    return ((ranks - 1.0) / (len(clipped) - 1.0) * 100.0).astype(float)


def _assign_revision_identity(frame: pd.DataFrame, config: RollingOversoldConfig) -> None:
    defaults: dict[str, Any] = {
        "snapshot_id": pd.NA,
        "anchor_date": config.anchor_start_date,
        "data_cutoff_date": config.anchor_start_date,
        "score_version": config.score_version,
        "previous_snapshot_id": pd.NA,
        "rank_delta": pd.NA,
        "lifecycle_delta": pd.NA,
    }
    for column, default in defaults.items():
        if column not in frame:
            frame[column] = default
        else:
            frame[column] = frame[column].where(frame[column].notna(), default)


def _output_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in _OUTPUT_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    return result.loc[:, list(_OUTPUT_COLUMNS)].reset_index(drop=True)


def _empty_result() -> pd.DataFrame:
    empty = pd.DataFrame(columns=_OUTPUT_COLUMNS)
    empty["stock_rank"] = empty["stock_rank"].astype("int64")
    return empty
