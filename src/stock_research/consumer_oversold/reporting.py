from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import uuid
from datetime import date, datetime
from pathlib import Path, PurePath
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

from .contracts import (
    UNIFIED_OUTPUT_FILENAMES,
    V2_OUTPUT_FILENAMES,
    validate_trade_date,
)
from .evidence import OUTPUT_COLUMNS as EVIDENCE_OUTPUT_COLUMNS
from .evidence import _valid_source_url


REPORT_COLUMNS = (
    "asset_id",
    "stock_code",
    "stock_name",
    "consumer_subindustry",
    "repair_bucket",
    "bucket_rank",
    "return_6m",
    "max_drawdown_12m",
    "relative_return_6m",
    "valuation_method",
    "valuation_percentile",
    "pessimistic_upside",
    "base_upside",
    "optimistic_upside",
    "repair_thesis",
    "unrepaired_metrics",
    "leading_indicator",
    "expected_validation_date",
    "source_title",
    "source_url",
    "source_publish_date",
    "main_risks",
    "invalidation_conditions",
    "operating_gap_score",
    "repair_potential_score",
    "valuation_repair_score",
    "oversold_score",
    "balance_sheet_score",
    "catalyst_verifiability_score",
    "priced_in_penalty",
    "composite_score",
    "exclusion_reasons",
)

_FRAME_KEYS = (
    "evidence",
    "scores",
    "exclusions",
    "top20",
    "reserve",
    "preaudit",
    "comparison",
)
_PAYLOAD_KEYS = ("trade_date", *_FRAME_KEYS, "coverage")
_V2_FRAME_KEYS = tuple(
    key for key in V2_OUTPUT_FILENAMES if key not in {"coverage", "report"}
)
_V2_PAYLOAD_KEYS = ("trade_date", *_V2_FRAME_KEYS, "coverage")
_COVERAGE_KEYS = (
    "funnel",
    "data_date_maxima",
    "missing_field_counts",
    "warnings",
    "valuation_history_coverage",
    "finance_history_coverage",
    "unified_funnel",
    "publication_status",
)
_FUNNEL_KEYS = (
    "raw_assets",
    "consumer_universe",
    "market_eligible",
    "oversold_eligible",
    "hard_risk_clear",
    "evidence_complete",
    "valuation_eligible",
    "selected_expected",
    "selected_early",
)
_SELECTED_GATES = {
    "evidence_complete": True,
    "eligible": True,
    "elasticity_coverage": True,
}
_UNIFIED_FUNNEL_KEYS = (
    "full",
    "automatic",
    "preaudit",
    "evidence_reviewed",
    "evidence_complete",
    "elasticity_complete",
    "final",
    "reserve",
)
_PUBLICATION_STATUSES = {"ready", "coverage_insufficient", "preaudit_only"}
_V2_FINAL_TOP_N = 20
_V2_RESERVE_TOP_N = 20
_V2_ACTIVATION_COMPONENTS = (
    "technical_readiness_score",
    "continuation_character_score",
    "residual_price_space_score",
    "capital_efficiency_score",
    "catalyst_timing_score",
)
_V2_SELECTED_REQUIRED_COLUMNS = (
    "asset_id",
    "final_rank",
    "ranking_version",
    "final_rank_score_v2",
    "repair_rank_percentile",
    "activation_rank_percentile",
    "composite_score",
    "activation_score",
    "technical_readiness_score",
    "continuation_character_score",
    "residual_price_space_score",
    "capital_efficiency_score",
    "catalyst_timing_score",
    "evidence_complete",
    "eligible",
    "activation_coverage",
    "activation_eligible",
    "activation_exclusion_reasons",
    "falling_knife",
    "overextended",
)
_V2_COMPARISON_REQUIRED_COLUMNS = (
    "asset_id",
    "v1_rank",
    "v2_rank",
    "rank_change",
    "v1_final_rank_score",
    "v1_repair_score",
    "v1_elasticity_score",
    "v2_repair_score",
    "v2_activation_score",
    "v2_final_rank_score",
    "v1_exclusion_reasons",
    "v2_exclusion_reasons",
)
_STAGING_PREFIX = ".consumer-oversold-staging-"
_TEMP_LINK_PREFIX = ".consumer-oversold-current-tmp-"
_RELEASE_PREFIX = "consumer-oversold-"


def _missing_keys(mapping: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if key not in mapping]


def _ordered_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if result.empty and "asset_id" not in result.columns:
        result = result.reindex(columns=["asset_id", *result.columns])
    preferred = [column for column in REPORT_COLUMNS if column in result.columns]
    extras = sorted(column for column in result.columns if column not in preferred)
    return result.loc[:, [*preferred, *extras]]


def _ordered_evidence_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    missing = [column for column in EVIDENCE_OUTPUT_COLUMNS if column not in result.columns]
    if missing:
        raise ValueError(f"evidence missing validated columns: {', '.join(missing)}")
    preferred = [column for column in EVIDENCE_OUTPUT_COLUMNS if column in result.columns]
    extras = sorted(column for column in result.columns if column not in preferred)
    return result.loc[:, [*preferred, *extras]]


def _validate_assets(frame: pd.DataFrame, name: str) -> tuple[list[str], set[str]]:
    if frame.empty:
        return [], set()
    if "asset_id" not in frame.columns:
        raise ValueError(f"{name} missing required columns: asset_id")
    missing = frame["asset_id"].isna()
    normalized = frame["asset_id"].astype(str).str.strip()
    if (missing | normalized.eq("")).any():
        raise ValueError(f"{name} asset_id must be non-empty")
    if normalized.duplicated().any():
        raise ValueError(f"{name} asset_id must be unique")
    return normalized.tolist(), set(normalized)


def _validate_selected(
    frame: pd.DataFrame,
    name: str,
    expected_ranks: range,
) -> set[str]:
    if frame.empty:
        return set()
    required_columns = ("asset_id", "final_rank", *_SELECTED_GATES)
    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"{name} missing required columns: {', '.join(missing_columns)}")
    _, assets = _validate_assets(frame, name)
    ranks: list[int] = []
    for value in frame["final_rank"]:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} field final_rank must contain strict integers")
        ranks.append(int(value))
    if ranks != list(expected_ranks):
        raise ValueError(f"{name} final_rank must equal {list(expected_ranks)}")
    for field, required in _SELECTED_GATES.items():
        valid = frame[field].map(
            lambda value: isinstance(value, (bool, np.bool_)) and bool(value) is required
        )
        if not valid.all():
            raise ValueError(f"{name} field {field} must be {str(required).lower()}")
    return assets


def _finite_score(value: Any) -> bool:
    return (
        not isinstance(value, (bool, np.bool_))
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def _is_missing_scalar(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _validate_v2_weight_maps(coverage: dict[str, Any]) -> dict[str, dict[str, float]]:
    required = {
        "v2_rank_weights": ("repair", "activation"),
        "v2_activation_weights": (
            "technical_readiness",
            "continuation_character",
            "residual_price_space",
            "capital_efficiency",
            "catalyst_timing",
        ),
    }
    normalized: dict[str, dict[str, float]] = {}
    for mapping_name, keys in required.items():
        mapping = coverage.get(mapping_name)
        if not isinstance(mapping, dict):
            raise ValueError(f"coverage {mapping_name} must be a dict")
        missing = [key for key in keys if key not in mapping]
        if missing:
            raise ValueError(
                f"coverage {mapping_name} missing required keys: {', '.join(missing)}"
            )
        values: dict[str, float] = {}
        for key in keys:
            value = mapping[key]
            if not _finite_score(value):
                raise ValueError(f"coverage {mapping_name} {key} must be finite")
            number = float(value)
            if not 0.0 <= number <= 1.0:
                raise ValueError(
                    f"coverage {mapping_name} {key} must be between 0 and 1"
                )
            values[key] = number
        if math.fsum(values.values()) != 1.0:
            raise ValueError(f"coverage {mapping_name} weights must sum to 1.0")
        normalized[mapping_name] = values
    return normalized


def _reason_text(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _validate_v2_activation_truth(
    frame: pd.DataFrame,
    name: str,
    coverage: dict[str, Any],
) -> None:
    weights = _validate_v2_weight_maps(coverage)["v2_activation_weights"]
    weight_values = (
        float(weights["technical_readiness"]),
        float(weights["continuation_character"]),
        float(weights["residual_price_space"]),
        float(weights["capital_efficiency"]),
        float(weights["catalyst_timing"]),
    )
    for _, row in frame.iterrows():
        activation_coverage = row["activation_coverage"]
        activation_eligible = row["activation_eligible"]
        eligible = row["eligible"]
        for field, value in (
            ("activation_coverage", activation_coverage),
            ("activation_eligible", activation_eligible),
            ("eligible", eligible),
            ("falling_knife", row["falling_knife"]),
            ("overextended", row["overextended"]),
        ):
            if not isinstance(value, (bool, np.bool_)):
                raise ValueError(f"{name} {field} must contain strict booleans")
        if bool(activation_eligible) and not bool(activation_coverage):
            raise ValueError(f"{name} activation_eligible requires activation_coverage")
        if bool(activation_eligible) and not bool(eligible):
            raise ValueError(f"{name} activation_eligible requires eligible")
        if bool(activation_eligible) and bool(row["falling_knife"]):
            raise ValueError(
                f"{name} activation_eligible cannot be true when falling_knife"
            )
        if bool(activation_eligible) and bool(row["overextended"]):
            raise ValueError(
                f"{name} activation_eligible cannot be true when overextended"
            )
        reasons = _reason_text(row["activation_exclusion_reasons"])
        if bool(row["falling_knife"]) and "falling_knife" not in reasons:
            raise ValueError(f"{name} falling_knife requires an exclusion reason")
        if bool(row["overextended"]) and "overextended" not in reasons:
            raise ValueError(f"{name} overextended requires an exclusion reason")
        if not bool(activation_eligible) and not reasons:
            raise ValueError(f"{name} ineligible activation requires an exclusion reason")
        if not bool(activation_coverage):
            continue
        component_values: list[float] = []
        for field in _V2_ACTIVATION_COMPONENTS:
            value = row[field]
            if not _finite_score(value):
                raise ValueError(f"{name} {field} must be finite")
            number = float(value)
            if not 0.0 <= number <= 100.0:
                raise ValueError(
                    f"{name} {field} must be between 0 and 100"
                )
            component_values.append(number)
        activation_score = row["activation_score"]
        if not _finite_score(activation_score):
            raise ValueError(f"{name} activation_score must be finite")
        expected = sum(
            weight * component
            for weight, component in zip(weight_values, component_values)
        )
        if not math.isclose(
            float(activation_score), expected, rel_tol=0.0, abs_tol=1e-8
        ):
            raise ValueError(
                f"{name} activation_score must equal weighted activation components"
            )


def _validate_v2_rank_frame(
    frame: pd.DataFrame,
    name: str,
    *,
    start_rank: int,
    coverage: dict[str, Any],
) -> list[str]:
    missing_columns = [
        column for column in _V2_SELECTED_REQUIRED_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(f"{name} missing required columns: {', '.join(missing_columns)}")
    asset_ids, _ = _validate_assets(frame, name)
    ranks: list[int] = []
    for value in frame["final_rank"]:
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)
        ):
            raise ValueError(f"{name} final_rank must contain strict integers")
        ranks.append(int(value))
    expected_ranks = list(range(start_rank, start_rank + len(frame)))
    if ranks != expected_ranks:
        raise ValueError(f"{name} final_rank must be continuous from {start_rank}")
    if not frame["ranking_version"].map(
        lambda value: isinstance(value, str) and value == "v2"
    ).all():
        raise ValueError(f"{name} ranking_version must be v2")
    _validate_v2_activation_truth(frame, name, coverage)
    rank_weights = _validate_v2_weight_maps(coverage)["v2_rank_weights"]
    for _, row in frame.iterrows():
        repair_percentile = row["repair_rank_percentile"]
        activation_percentile = row["activation_rank_percentile"]
        final_score = row["final_rank_score_v2"]
        for field, value in (
            ("repair_rank_percentile", repair_percentile),
            ("activation_rank_percentile", activation_percentile),
            ("final_rank_score_v2", final_score),
        ):
            if not _finite_score(value):
                raise ValueError(f"{name} {field} must be finite")
        for field, value in (
            ("repair_rank_percentile", repair_percentile),
            ("activation_rank_percentile", activation_percentile),
        ):
            if not 0.0 <= float(value) <= 100.0:
                raise ValueError(f"{name} {field} must be between 0 and 100")
        if not _finite_score(row["composite_score"]):
            raise ValueError(f"{name} composite_score must be finite")
        expected_score = (
            rank_weights["repair"] * float(repair_percentile)
            + rank_weights["activation"] * float(activation_percentile)
        )
        if not math.isclose(
            float(final_score), expected_score, rel_tol=0.0, abs_tol=1e-8
        ):
            raise ValueError(
                f"{name} final_rank_score_v2 must equal weighted rank components"
            )
    for field in (
        "evidence_complete",
        "eligible",
        "activation_coverage",
        "activation_eligible",
    ):
        valid = frame[field].map(
            lambda value: isinstance(value, (bool, np.bool_)) and bool(value)
        )
        if not valid.all():
            raise ValueError(f"{name} {field} must be true")
    return asset_ids


def _validate_v2_selection_values(
    selection: pd.DataFrame,
    ranked_slice: pd.DataFrame,
    name: str,
) -> None:
    if selection.columns.tolist() != ranked_slice.columns.tolist():
        raise ValueError(f"{name} columns must exactly equal ranked_pool")
    try:
        pd.testing.assert_frame_equal(
            selection.reset_index(drop=True),
            ranked_slice.reset_index(drop=True),
            check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError(f"{name} must exactly equal ranked_pool slice") from exc


def validate_v2_snapshot_rank_frames(
    frames: dict[str, pd.DataFrame],
    *,
    coverage: dict[str, Any],
    trade_date: str,
) -> dict[str, int]:
    """Validate the sealed V2 ranking frames before forward evaluation."""
    required = ("top20", "top30", "ranked_pool")
    missing = [name for name in required if name not in frames]
    if missing:
        raise ValueError(
            "sealed V2 snapshot missing ranking frames: " + ", ".join(missing)
        )
    normalized_trade_date = validate_trade_date(trade_date)
    if coverage.get("trade_date") != normalized_trade_date:
        raise ValueError("sealed V2 snapshot coverage trade_date must match trade_date")
    if coverage.get("ranking_version") != "v2":
        raise ValueError("sealed V2 snapshot coverage ranking_version must be v2")

    for name in required:
        frame = frames[name]
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"sealed V2 snapshot {name} must be a pandas DataFrame")
        missing_columns = [
            field
            for field in ("ranking_version", "trade_date")
            if field not in frame.columns
        ]
        if missing_columns:
            raise ValueError(
                f"sealed V2 snapshot {name} missing required columns: "
                + ", ".join(missing_columns)
            )
        versions = frame["ranking_version"]
        if versions.nunique(dropna=False) > 1:
            raise ValueError(
                f"sealed V2 snapshot {name} ranking_version must be single-valued"
            )
        if not versions.map(
            lambda value: isinstance(value, str) and value == "v2"
        ).all():
            raise ValueError(f"sealed V2 snapshot {name} ranking_version must be v2")
        dates = frame["trade_date"]
        if dates.nunique(dropna=False) > 1:
            raise ValueError(
                f"sealed V2 snapshot {name} trade_date must be single-valued"
            )
        if not dates.map(
            lambda value: isinstance(value, str) and value == normalized_trade_date
        ).all():
            raise ValueError(
                f"sealed V2 snapshot {name} trade_date must equal coverage trade_date"
            )

    ranked_pool = frames["ranked_pool"]
    ranked_ids = _validate_v2_rank_frame(
        ranked_pool, "sealed V2 snapshot ranked_pool", start_rank=1, coverage=coverage
    )
    order_fields = (
        "final_rank_score_v2",
        "activation_rank_percentile",
        "repair_rank_percentile",
    )
    order_values = ranked_pool.loc[:, order_fields].apply(
        pd.to_numeric, errors="coerce"
    )
    if order_values.isna().any().any() or not np.isfinite(order_values).all().all():
        raise ValueError("sealed V2 snapshot ranked_pool score ordering fields must be finite")
    expected_ranked_ids = (
        ranked_pool.sort_values(
            [*order_fields, "asset_id"],
            ascending=[False, False, False, True],
            kind="stable",
        )["asset_id"]
        .astype(str)
        .str.strip()
        .tolist()
    )
    if ranked_ids != expected_ranked_ids:
        raise ValueError("sealed V2 snapshot ranked_pool order is invalid")

    final_top_n = _positive_size(coverage, "final_top_n", _V2_FINAL_TOP_N)
    if final_top_n != _V2_FINAL_TOP_N:
        raise ValueError("sealed V2 snapshot coverage final_top_n must equal 20")
    reserve_top_n = _positive_size(coverage, "reserve_top_n", _V2_RESERVE_TOP_N)
    if reserve_top_n != _V2_RESERVE_TOP_N:
        raise ValueError("sealed V2 snapshot coverage reserve_top_n must equal 20")
    expected_counts = {
        "ranked_pool": len(ranked_ids),
        "top20": min(final_top_n, len(ranked_ids)),
        "top30": min(30, len(ranked_ids)),
    }
    for name, expected_count in expected_counts.items():
        actual_count = len(frames[name])
        if actual_count != expected_count:
            raise ValueError(
                f"sealed V2 snapshot {name} length must equal ranked_pool selection size"
            )
        coverage_key = {
            "ranked_pool": "v2_ranked_pool_count",
            "top30": "v2_top30_count",
        }.get(name)
        if coverage_key is not None:
            if coverage_key not in coverage:
                raise ValueError(
                    f"sealed V2 snapshot coverage missing {coverage_key}"
                )
            if _coverage_count(coverage, coverage_key, "sealed V2 snapshot coverage") != actual_count:
                raise ValueError(
                    f"sealed V2 snapshot coverage {coverage_key} must equal {name} length"
                )

    top20_ids = _validate_v2_rank_frame(
        frames["top20"], "sealed V2 snapshot top20", start_rank=1, coverage=coverage
    )
    top30_ids = _validate_v2_rank_frame(
        frames["top30"], "sealed V2 snapshot top30", start_rank=1, coverage=coverage
    )
    if top20_ids != ranked_ids[: expected_counts["top20"]]:
        raise ValueError("sealed V2 snapshot top20 must equal ranked_pool prefix")
    if top30_ids != ranked_ids[: expected_counts["top30"]]:
        raise ValueError("sealed V2 snapshot top30 must equal ranked_pool prefix")
    _validate_v2_selection_values(
        frames["top20"], ranked_pool.iloc[: expected_counts["top20"]], "sealed V2 snapshot top20"
    )
    _validate_v2_selection_values(
        frames["top30"], ranked_pool.iloc[: expected_counts["top30"]], "sealed V2 snapshot top30"
    )
    return expected_counts


def _validate_v2_comparison_truth(
    comparison: pd.DataFrame,
    ranked_pool: pd.DataFrame,
    scores: pd.DataFrame,
) -> None:
    _, ranked_ids = _validate_assets(ranked_pool, "ranked_pool")
    _, comparison_ids = _validate_assets(comparison, "comparison")
    _, score_ids = _validate_assets(scores, "scores")
    if not ranked_ids.issubset(comparison_ids):
        raise ValueError("comparison must cover every ranked_pool asset")
    if not ranked_ids.issubset(score_ids):
        raise ValueError("ranked_pool must be covered by scores")
    if comparison_ids != score_ids:
        raise ValueError("comparison must exactly cover scores asset set")
    ranked_by_asset = ranked_pool.assign(
        _normalized_asset_id=ranked_pool["asset_id"].astype(str).str.strip()
    ).set_index("_normalized_asset_id", drop=False)
    scores_by_asset = scores.assign(
        _normalized_asset_id=scores["asset_id"].astype(str).str.strip()
    ).set_index("_normalized_asset_id", drop=False)
    comparison_by_asset = comparison.assign(
        _normalized_asset_id=comparison["asset_id"].astype(str).str.strip()
    ).set_index("_normalized_asset_id", drop=False)
    numeric_fields = (
        "v1_rank",
        "v2_rank",
        "rank_change",
        "v1_final_rank_score",
        "v1_repair_score",
        "v1_elasticity_score",
        "v2_repair_score",
        "v2_activation_score",
        "v2_final_rank_score",
    )
    for _, row in comparison.iterrows():
        for field in numeric_fields:
            value = row[field]
            if not _is_missing_scalar(value) and not _finite_score(value):
                raise ValueError(f"comparison {field} must be finite")
    for asset_id in ranked_ids:
        if _is_missing_scalar(comparison_by_asset.loc[asset_id, "v2_rank"]):
            raise ValueError(
                "comparison v2_rank must be present for every ranked_pool asset"
            )
    for _, row in comparison.iterrows():
        asset_id = str(row["asset_id"]).strip()
        v2_rank = row["v2_rank"]
        ranked = asset_id in ranked_by_asset.index
        ranked_row = ranked_by_asset.loc[asset_id] if ranked else None
        scores_row = scores_by_asset.loc[asset_id]

        for field, score_field in (
            ("v2_repair_score", "composite_score"),
            ("v2_activation_score", "activation_score"),
        ):
            value = row[field]
            expected = scores_row[score_field]
            if _is_missing_scalar(expected):
                if not _is_missing_scalar(value):
                    raise ValueError(f"comparison {field} must match scores")
            elif not _finite_score(expected):
                raise ValueError(f"scores {score_field} must be finite")
            elif _is_missing_scalar(value) or not math.isclose(
                float(value), float(expected), rel_tol=0.0, abs_tol=1e-8
            ):
                target = "ranked_pool" if ranked else "scores"
                raise ValueError(f"comparison {field} must match {target}")

        if ranked:
            if not _finite_score(v2_rank) or not float(v2_rank).is_integer():
                raise ValueError("comparison v2_rank must contain strict integers")
            if int(v2_rank) != int(ranked_row["final_rank"]):
                raise ValueError("comparison v2_rank must match ranked_pool")
            for field, ranked_field in (
                ("v2_repair_score", "composite_score"),
                ("v2_activation_score", "activation_score"),
                ("v2_final_rank_score", "final_rank_score_v2"),
            ):
                value = row[field]
                expected = ranked_row[ranked_field]
                if not _finite_score(expected) or _is_missing_scalar(value) or not math.isclose(
                    float(value), float(expected), rel_tol=0.0, abs_tol=1e-8
                ):
                    raise ValueError(f"comparison {field} must match ranked_pool")
        else:
            if not _is_missing_scalar(v2_rank):
                raise ValueError("comparison v2_rank asset must be present in ranked_pool")
            if not _is_missing_scalar(row["v2_final_rank_score"]):
                raise ValueError(
                    "comparison v2_final_rank_score must be missing for non-ranked asset"
                )
            if not _is_missing_scalar(row["rank_change"]):
                raise ValueError(
                    "comparison rank_change must be missing for non-ranked asset"
                )
        v1_rank = row["v1_rank"]
        rank_change = row["rank_change"]
        if not _is_missing_scalar(v1_rank) and (
            not _finite_score(v1_rank) or not float(v1_rank).is_integer()
        ):
            raise ValueError("comparison v1_rank must contain strict integers")
        if ranked:
            if _is_missing_scalar(v1_rank):
                if not _is_missing_scalar(rank_change):
                    raise ValueError(
                        "comparison rank_change must equal v1_rank - v2_rank"
                    )
            else:
                expected_change = float(v1_rank) - float(v2_rank)
                if not _finite_score(rank_change) or not math.isclose(
                    float(rank_change), expected_change, rel_tol=0.0, abs_tol=1e-8
                ):
                    raise ValueError(
                        "comparison rank_change must equal v1_rank - v2_rank"
                    )


def _validate_v2_frames(
    frames: dict[str, pd.DataFrame],
    coverage: dict[str, Any],
) -> dict[str, int]:
    _validate_v2_weight_maps(coverage)
    missing_score_columns = [
        column
        for column in ("asset_id", "composite_score", "activation_score")
        if column not in frames["scores"].columns
    ]
    if missing_score_columns:
        raise ValueError(
            "scores missing required columns: " + ", ".join(missing_score_columns)
        )
    missing_comparison = [
        column
        for column in _V2_COMPARISON_REQUIRED_COLUMNS
        if column not in frames["comparison"].columns
    ]
    if missing_comparison:
        raise ValueError(
            "comparison missing required columns: " + ", ".join(missing_comparison)
        )
    _validate_assets(frames["comparison"], "comparison")
    ranked_ids = _validate_v2_rank_frame(
        frames["ranked_pool"], "ranked_pool", start_rank=1, coverage=coverage
    )
    ranked_pool = frames["ranked_pool"]
    order_fields = (
        "final_rank_score_v2",
        "activation_rank_percentile",
        "repair_rank_percentile",
    )
    order_values = ranked_pool.loc[:, order_fields].apply(
        pd.to_numeric, errors="coerce"
    )
    if order_values.isna().any().any() or not np.isfinite(order_values).all().all():
        raise ValueError("ranked_pool V2 score ordering fields must be finite")
    expected_ranked_ids = (
        ranked_pool.sort_values(
            [*order_fields, "asset_id"],
            ascending=[False, False, False, True],
            kind="stable",
        )["asset_id"]
        .astype(str)
        .str.strip()
        .tolist()
    )
    if ranked_ids != expected_ranked_ids:
        raise ValueError("ranked_pool order must follow V2 score ordering")
    final_top_n = _positive_size(coverage, "final_top_n", _V2_FINAL_TOP_N)
    reserve_top_n = _positive_size(
        coverage, "reserve_top_n", _V2_RESERVE_TOP_N
    )
    if final_top_n != _V2_FINAL_TOP_N:
        raise ValueError("coverage final_top_n must equal 20 for v2")
    if reserve_top_n != _V2_RESERVE_TOP_N:
        raise ValueError("coverage reserve_top_n must equal 20 for v2")
    top20_ids = _validate_v2_rank_frame(
        frames["top20"], "top20", start_rank=1, coverage=coverage
    )
    top30_ids = _validate_v2_rank_frame(
        frames["top30"], "top30", start_rank=1, coverage=coverage
    )
    reserve_ids = _validate_v2_rank_frame(
        frames["reserve"],
        "reserve",
        start_rank=final_top_n + 1,
        coverage=coverage,
    )
    pool_size = len(ranked_ids)
    expected_top20_count = min(final_top_n, pool_size)
    expected_top30_count = min(30, pool_size)
    expected_reserve_count = min(reserve_top_n, max(0, pool_size - final_top_n))
    for name, actual_count, expected_count in (
        ("top20", len(top20_ids), expected_top20_count),
        ("top30", len(top30_ids), expected_top30_count),
        ("reserve", len(reserve_ids), expected_reserve_count),
    ):
        if actual_count != expected_count:
            raise ValueError(f"{name} length must equal ranked_pool selection size")
    if top20_ids != ranked_ids[:expected_top20_count]:
        raise ValueError("top20 must equal the ranked_pool prefix")
    if top30_ids != ranked_ids[:expected_top30_count]:
        raise ValueError("top30 must equal the ranked_pool prefix")
    expected_reserve_ids = ranked_ids[
        final_top_n : final_top_n + expected_reserve_count
    ]
    if reserve_ids != expected_reserve_ids:
        raise ValueError("reserve must follow top20 in ranked_pool order")
    _validate_v2_selection_values(
        frames["top20"], ranked_pool.iloc[:expected_top20_count], "top20"
    )
    _validate_v2_selection_values(
        frames["top30"], ranked_pool.iloc[:expected_top30_count], "top30"
    )
    _validate_v2_selection_values(
        frames["reserve"],
        ranked_pool.iloc[final_top_n : final_top_n + expected_reserve_count],
        "reserve",
    )
    _validate_v2_comparison_truth(
        frames["comparison"], ranked_pool, frames["scores"]
    )
    preaudit_ids = _validate_assets(frames["preaudit"], "preaudit")[1]
    selected_ids = set(top20_ids) | set(top30_ids) | set(reserve_ids)
    if not selected_ids.issubset(preaudit_ids):
        raise ValueError("selected assets must be present in preaudit")
    return {
        "ranked_pool": pool_size,
        "top20": len(top20_ids),
        "top30": len(top30_ids),
        "reserve": len(reserve_ids),
        "preaudit": len(preaudit_ids),
    }


def _json_safe(value: Any, path: str = "coverage") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{path} must contain only finite JSON values")
        return number
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} object keys must be strings")
            result[key] = _json_safe(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains a value that is not JSON-safe: {type(value).__name__}")


def _positive_size(coverage: dict[str, Any], key: str, default: int) -> int:
    value = coverage.get(key, default)
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"coverage {key} must be an integer")
    if int(value) < 1:
        raise ValueError(f"coverage {key} must be positive")
    return int(value)


def _normalize_coverage(
    coverage: dict[str, Any],
    trade_date: str,
    *,
    top20_count: int,
    reserve_count: int,
    preaudit_count: int,
) -> dict[str, Any]:
    missing = _missing_keys(coverage, _COVERAGE_KEYS)
    if missing:
        raise ValueError(f"coverage missing required keys: {', '.join(missing)}")
    if not isinstance(coverage["funnel"], dict):
        raise TypeError("coverage funnel must be a dict")
    missing_funnel = _missing_keys(coverage["funnel"], _FUNNEL_KEYS)
    if missing_funnel:
        raise ValueError(f"coverage funnel missing required keys: {', '.join(missing_funnel)}")
    for key in _FUNNEL_KEYS:
        value = coverage["funnel"][key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise TypeError(f"coverage funnel {key} must be an integer")
        if int(value) < 0:
            raise ValueError(f"coverage funnel {key} must be non-negative")
    ordered = [int(coverage["funnel"][key]) for key in _FUNNEL_KEYS[:7]]
    if any(left < right for left, right in zip(ordered, ordered[1:])):
        raise ValueError("coverage funnel counts must be non-increasing")
    selected_expected = int(coverage["funnel"]["selected_expected"])
    selected_early = int(coverage["funnel"]["selected_early"])
    if ordered[-1] < selected_expected + selected_early:
        raise ValueError(
            "coverage valuation_eligible must be at least selected_expected + selected_early"
        )
    if not isinstance(coverage["unified_funnel"], dict):
        raise TypeError("coverage unified_funnel must be a dict")
    missing_unified = _missing_keys(coverage["unified_funnel"], _UNIFIED_FUNNEL_KEYS)
    if missing_unified:
        raise ValueError(
            f"coverage unified_funnel missing required keys: {', '.join(missing_unified)}"
        )
    for key in _UNIFIED_FUNNEL_KEYS:
        value = coverage["unified_funnel"][key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise TypeError(f"coverage unified_funnel {key} must be an integer")
        if int(value) < 0:
            raise ValueError(f"coverage unified_funnel {key} must be non-negative")
    unified = {
        key: int(coverage["unified_funnel"][key]) for key in _UNIFIED_FUNNEL_KEYS
    }
    if not unified["full"] >= unified["automatic"] >= unified["preaudit"]:
        raise ValueError(
            "coverage unified_funnel must satisfy full >= automatic >= preaudit"
        )
    if not (
        unified["preaudit"]
        >= unified["evidence_reviewed"]
        >= unified["evidence_complete"]
    ):
        raise ValueError(
            "coverage unified_funnel must satisfy "
            "preaudit >= evidence_reviewed >= evidence_complete"
        )
    if unified["preaudit"] < unified["elasticity_complete"]:
        raise ValueError(
            "coverage unified_funnel preaudit must be at least elasticity_complete"
        )
    if unified["evidence_complete"] < unified["elasticity_complete"]:
        raise ValueError(
            "coverage unified_funnel evidence_complete must be at least "
            "elasticity_complete"
        )
    status = coverage["publication_status"]
    if status not in _PUBLICATION_STATUSES:
        raise ValueError(
            "coverage publication_status must be ready, coverage_insufficient, "
            "or preaudit_only"
        )
    final_top_n = _positive_size(coverage, "final_top_n", 20)
    reserve_top_n = _positive_size(coverage, "reserve_top_n", 20)
    preaudit_size = _positive_size(coverage, "preaudit_size", 60)
    minimum_evidence_complete = _positive_size(
        coverage, "minimum_evidence_complete", final_top_n + reserve_top_n
    )
    if preaudit_size < final_top_n + reserve_top_n:
        raise ValueError("coverage preaudit_size must cover final_top_n plus reserve_top_n")
    if minimum_evidence_complete < final_top_n + reserve_top_n:
        raise ValueError(
            "coverage minimum_evidence_complete must cover final_top_n plus reserve_top_n"
        )
    if minimum_evidence_complete > preaudit_size:
        raise ValueError(
            "coverage minimum_evidence_complete must not exceed preaudit_size"
        )
    if preaudit_count > preaudit_size:
        raise ValueError("preaudit frame length must not exceed coverage preaudit_size")
    if status == "ready":
        if top20_count != final_top_n:
            raise ValueError("ready publication top20 length must equal final_top_n")
        if reserve_count != reserve_top_n:
            raise ValueError("ready publication reserve length must equal reserve_top_n")
        selected_count = top20_count + reserve_count
        if unified["evidence_complete"] < minimum_evidence_complete:
            raise ValueError(
                "ready publication evidence_complete must meet minimum_evidence_complete"
            )
        if unified["evidence_complete"] < selected_count:
            raise ValueError(
                "ready publication evidence_complete must cover final plus reserve"
            )
        if unified["elasticity_complete"] < selected_count:
            raise ValueError(
                "ready publication elasticity_complete must cover final plus reserve"
            )
    elif top20_count or reserve_count:
        raise ValueError("coverage_insufficient publication must not publish ranked selections")
    if unified["preaudit"] != preaudit_count:
        raise ValueError("coverage unified_funnel preaudit must equal preaudit frame length")
    if unified["final"] != top20_count:
        raise ValueError("coverage unified_funnel final must equal top20 frame length")
    if unified["reserve"] != reserve_count:
        raise ValueError("coverage unified_funnel reserve must equal reserve frame length")
    normalized = _json_safe(copy.deepcopy(coverage))
    normalized["trade_date"] = trade_date
    normalized.update(
        final_top_n=final_top_n,
        reserve_top_n=reserve_top_n,
        preaudit_size=preaudit_size,
        minimum_evidence_complete=minimum_evidence_complete,
    )
    warning = (
        "publication_thresholds: "
        f"final_top_n={final_top_n}, reserve_top_n={reserve_top_n}, "
        f"preaudit_size={preaudit_size}, "
        f"minimum_evidence_complete={minimum_evidence_complete}"
    )
    warnings = normalized["warnings"]
    if not isinstance(warnings, list):
        raise TypeError("coverage warnings must be a list")
    normalized["warnings"] = [*warnings, warning] if warning not in warnings else warnings
    return normalized


def _coverage_count(mapping: dict[str, Any], key: str, path: str) -> int:
    value = mapping.get(key)
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, np.integer)
    ):
        raise TypeError(f"{path} {key} must be an integer")
    if int(value) < 0:
        raise ValueError(f"{path} {key} must be non-negative")
    return int(value)


def _validate_date_maxima(value: Any, *, cutoff: str, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            _validate_date_maxima(item, cutoff=cutoff, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            _validate_date_maxima(item, cutoff=cutoff, path=f"{path}[{index}]")
        return
    if value is None:
        return
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{path} must be a valid date not later than {cutoff}")
    if not isinstance(value, (str, date, datetime, pd.Timestamp)):
        raise ValueError(f"{path} must be a valid date not later than {cutoff}")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be a valid date not later than {cutoff}") from exc
    if pd.isna(parsed):
        raise ValueError(f"{path} must be a valid date not later than {cutoff}")
    if parsed.date() > date.fromisoformat(cutoff):
        raise ValueError(f"{path} must not be later than trade_date {cutoff}")


def _walk_coverage_date_maxima(
    value: Any,
    *,
    cutoff: str,
    path: str,
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            child_path = f"{path}.{key}"
            if "date_maxima" in key:
                _validate_date_maxima(item, cutoff=cutoff, path=child_path)
            else:
                _walk_coverage_date_maxima(item, cutoff=cutoff, path=child_path)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            _walk_coverage_date_maxima(
                item,
                cutoff=cutoff,
                path=f"{path}[{index}]",
            )


def _validate_coverage_date_maxima(
    coverage: dict[str, Any],
    *,
    cutoff: str,
    path: str = "coverage",
) -> None:
    _walk_coverage_date_maxima(coverage, cutoff=cutoff, path=path)


def _normalize_v2_coverage(
    coverage: dict[str, Any],
    trade_date: str,
    *,
    frame_counts: dict[str, int],
) -> dict[str, Any]:
    missing = _missing_keys(coverage, _COVERAGE_KEYS)
    if missing:
        raise ValueError(f"coverage missing required keys: {', '.join(missing)}")
    if coverage.get("ranking_version") != "v2":
        raise ValueError("coverage ranking_version must be v2")
    coverage_trade_date = coverage.get("trade_date")
    if coverage_trade_date is not None and coverage_trade_date != trade_date:
        raise ValueError("coverage trade_date must match payload trade_date")
    _validate_coverage_date_maxima(coverage, cutoff=trade_date)

    funnel = coverage["funnel"]
    if not isinstance(funnel, dict):
        raise TypeError("coverage funnel must be a dict")
    missing_funnel = _missing_keys(funnel, _FUNNEL_KEYS)
    if missing_funnel:
        raise ValueError(
            f"coverage funnel missing required keys: {', '.join(missing_funnel)}"
        )
    funnel_counts = {
        key: _coverage_count(funnel, key, "coverage funnel") for key in _FUNNEL_KEYS
    }
    ordered = [funnel_counts[key] for key in _FUNNEL_KEYS[:7]]
    if any(left < right for left, right in zip(ordered, ordered[1:])):
        raise ValueError("coverage funnel counts must be non-increasing")
    if ordered[-1] < (
        funnel_counts["selected_expected"] + funnel_counts["selected_early"]
    ):
        raise ValueError(
            "coverage valuation_eligible must be at least selected_expected + selected_early"
        )

    unified_funnel = coverage["unified_funnel"]
    if not isinstance(unified_funnel, dict):
        raise TypeError("coverage unified_funnel must be a dict")
    missing_unified = _missing_keys(unified_funnel, _UNIFIED_FUNNEL_KEYS)
    if missing_unified:
        raise ValueError(
            "coverage unified_funnel missing required keys: "
            + ", ".join(missing_unified)
        )
    unified = {
        key: _coverage_count(unified_funnel, key, "coverage unified_funnel")
        for key in _UNIFIED_FUNNEL_KEYS
    }
    ranked_count = frame_counts["ranked_pool"]
    for key in ("evidence_complete", "elasticity_complete"):
        if unified[key] < ranked_count:
            raise ValueError(
                f"unified_funnel {key} must cover ranked_pool"
            )
    if not unified["full"] >= unified["automatic"] >= unified["preaudit"]:
        raise ValueError(
            "coverage unified_funnel must satisfy full >= automatic >= preaudit"
        )
    if not (
        unified["preaudit"]
        >= unified["evidence_reviewed"]
        >= unified["evidence_complete"]
        >= unified["elasticity_complete"]
    ):
        raise ValueError(
            "coverage unified_funnel must satisfy preaudit >= evidence_reviewed >= "
            "evidence_complete >= elasticity_complete"
        )
    for key in ("preaudit", "final", "reserve"):
        expected = frame_counts[key if key != "final" else "top20"]
        if unified[key] != expected:
            frame_name = "top20" if key == "final" else key
            raise ValueError(
                f"coverage unified_funnel {key} must equal {frame_name} frame length"
            )

    activation_funnel = coverage.get("activation_funnel")
    if not isinstance(activation_funnel, dict):
        raise TypeError("coverage activation_funnel must be a dict")
    required_activation = (
        "first_gate_eligible",
        "activation_covered",
        "activation_eligible",
        "ranked_pool",
        "top20",
        "top30",
        "reserve",
    )
    missing_activation = _missing_keys(activation_funnel, required_activation)
    if missing_activation:
        raise ValueError(
            "coverage activation_funnel missing required keys: "
            + ", ".join(missing_activation)
        )
    activation = {
        key: _coverage_count(
            activation_funnel, key, "coverage activation_funnel"
        )
        for key in required_activation
    }
    for key in ("ranked_pool", "top20", "top30", "reserve"):
        if activation[key] != frame_counts[key]:
            raise ValueError(
                f"coverage activation_funnel {key} must equal {key} frame length"
            )
    if not (
        activation["first_gate_eligible"]
        >= activation["activation_covered"]
        >= activation["activation_eligible"]
        >= activation["ranked_pool"]
    ):
        raise ValueError(
            "coverage activation_funnel must satisfy first_gate_eligible >= "
            "activation_covered >= activation_eligible >= ranked_pool"
        )

    for key in ("v2_thresholds", "v2_rank_weights", "v2_activation_weights"):
        if not isinstance(coverage.get(key), dict):
            raise TypeError(f"coverage {key} must be a dict")
    required_thresholds = (
        "min_6m_return",
        "min_12m_drawdown",
        "min_relative_return",
        "min_base_upside",
        "min_composite_score",
        "min_technical_readiness_score",
    )
    required_rank_weights = ("repair", "activation")
    required_activation_weights = (
        "technical_readiness",
        "continuation_character",
        "residual_price_space",
        "capital_efficiency",
        "catalyst_timing",
    )
    for mapping_name, required in (
        ("v2_thresholds", required_thresholds),
        ("v2_rank_weights", required_rank_weights),
        ("v2_activation_weights", required_activation_weights),
    ):
        missing_values = _missing_keys(coverage[mapping_name], required)
        if missing_values:
            raise ValueError(
                f"coverage {mapping_name} missing required keys: "
                + ", ".join(missing_values)
            )
        for key in required:
            value = coverage[mapping_name][key]
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, float, np.integer, np.floating)
            ) or not math.isfinite(float(value)):
                raise ValueError(f"coverage {mapping_name} {key} must be finite")
    for mapping_name, required in (
        ("v2_rank_weights", required_rank_weights),
        ("v2_activation_weights", required_activation_weights),
    ):
        values = [float(coverage[mapping_name][key]) for key in required]
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError(f"coverage {mapping_name} weights must be between 0 and 1")
        if math.fsum(values) != 1.0:
            raise ValueError(f"coverage {mapping_name} weights must sum to 1.0")

    final_top_n = _positive_size(coverage, "final_top_n", _V2_FINAL_TOP_N)
    reserve_top_n = _positive_size(
        coverage, "reserve_top_n", _V2_RESERVE_TOP_N
    )
    if final_top_n != _V2_FINAL_TOP_N:
        raise ValueError("coverage final_top_n must equal 20 for v2")
    if reserve_top_n != _V2_RESERVE_TOP_N:
        raise ValueError("coverage reserve_top_n must equal 20 for v2")
    preaudit_size = _positive_size(coverage, "preaudit_size", 60)
    minimum_evidence_complete = _positive_size(
        coverage, "minimum_evidence_complete", final_top_n + reserve_top_n
    )
    if preaudit_size < final_top_n + reserve_top_n:
        raise ValueError("coverage preaudit_size must cover final_top_n plus reserve_top_n")
    if minimum_evidence_complete < final_top_n + reserve_top_n:
        raise ValueError(
            "coverage minimum_evidence_complete must cover final_top_n plus reserve_top_n"
        )
    if minimum_evidence_complete > preaudit_size:
        raise ValueError(
            "coverage minimum_evidence_complete must not exceed preaudit_size"
        )
    if "full_pool_evidence_complete" in coverage and _coverage_count(
        coverage, "full_pool_evidence_complete", "coverage"
    ) < ranked_count:
        raise ValueError("full_pool_evidence_complete must cover ranked_pool")
    if frame_counts["preaudit"] > preaudit_size:
        raise ValueError("preaudit frame length must not exceed coverage preaudit_size")
    if _coverage_count(coverage, "v2_ranked_pool_count", "coverage") != frame_counts[
        "ranked_pool"
    ]:
        raise ValueError("coverage v2_ranked_pool_count must equal ranked_pool length")
    if _coverage_count(coverage, "v2_top30_count", "coverage") != frame_counts["top30"]:
        raise ValueError("coverage v2_top30_count must equal top30 length")

    status = coverage["publication_status"]
    if status not in _PUBLICATION_STATUSES:
        raise ValueError(
            "coverage publication_status must be ready, coverage_insufficient, "
            "or preaudit_only"
        )
    ranked_count = frame_counts["ranked_pool"]
    if status == "preaudit_only":
        if any(frame_counts[key] for key in ("ranked_pool", "top20", "top30", "reserve")):
            raise ValueError("preaudit_only publication must not include ranked selections")
    else:
        expected_status = "ready" if ranked_count >= 30 else "coverage_insufficient"
        if status != expected_status:
            raise ValueError(
                f"coverage publication_status must be {expected_status} for ranked pool size"
            )

    normalized = _json_safe(copy.deepcopy(coverage))
    normalized["trade_date"] = trade_date
    normalized.update(
        final_top_n=final_top_n,
        reserve_top_n=reserve_top_n,
        preaudit_size=preaudit_size,
        minimum_evidence_complete=minimum_evidence_complete,
    )
    warnings = normalized["warnings"]
    if not isinstance(warnings, list):
        raise TypeError("coverage warnings must be a list")
    threshold_warning = (
        "publication_thresholds: "
        f"final_top_n={final_top_n}, reserve_top_n={reserve_top_n}, "
        f"preaudit_size={preaudit_size}, "
        f"minimum_evidence_complete={minimum_evidence_complete}"
    )
    if threshold_warning not in warnings:
        normalized["warnings"] = [*warnings, threshold_warning]
    if (
        status == "coverage_insufficient"
        and ranked_count < 30
        and "v2_ranked_pool_below_30" not in normalized["warnings"]
    ):
        normalized["warnings"] = [
            *normalized["warnings"],
            "v2_ranked_pool_below_30",
        ]
    return normalized


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    safe = frame.copy(deep=True)
    for column in safe.columns:
        safe[column] = safe[column].map(_escape_csv_formula)
    safe.to_csv(path, index=False, encoding="utf-8")
    _fsync_file(path)


def _write_text(text: str, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _dir_fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _escape_csv_formula(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _display(value: Any, *, percent: bool = False) -> str:
    if value is None or value is pd.NA:
        return "数据缺失"
    try:
        if pd.isna(value):
            return "数据缺失"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return "数据缺失"
    if percent and isinstance(value, (int, float, np.integer, np.floating)):
        return f"{float(value):.1%}"
    text = str(value).strip()
    return text if text else "数据缺失"


def _escape_markdown_text(value: Any) -> str:
    text = _display(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("\\", "\\\\")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in "[]()!*_`#":
        text = text.replace(character, f"\\{character}")
    return text.replace("|", "\\|")


def _escape_table(value: Any) -> str:
    return _escape_markdown_text(value)


def _escape_link_label(value: Any) -> str:
    return _escape_markdown_text(value)


def _percent_text(value: Any) -> str:
    return _escape_markdown_text(_display(value, percent=True))


def _score_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number):
            return f"{number:.1f}"
    return _escape_markdown_text(value)


def _market_cap_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number):
            return f"{number / 100_000_000:.2f} 亿元"
    return "数据缺失"


def _count_text(value: Any) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isfinite(number) and number.is_integer():
            return str(int(number))
    return _escape_markdown_text(value)


def _enrich_rows(primary: pd.DataFrame, supplemental: pd.DataFrame | None) -> pd.DataFrame:
    result = primary.copy(deep=True)
    if (
        result.empty
        or supplemental is None
        or supplemental.empty
        or "asset_id" not in result.columns
        or "asset_id" not in supplemental.columns
    ):
        return result
    lookup = supplemental.drop_duplicates("asset_id", keep="first").set_index("asset_id")
    missing_columns = [column for column in lookup.columns if column not in result.columns]
    if missing_columns:
        additions = lookup.reindex(result["asset_id"])[missing_columns].reset_index(drop=True)
        additions.index = result.index
        result = pd.concat([result, additions], axis=1)
    for column in (column for column in lookup.columns if column in primary.columns):
        mapped = result["asset_id"].map(lookup[column])
        result[column] = result[column].where(result[column].notna(), mapped)
    return result


def _valid_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value
    if (
        not url
        or url != url.strip()
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)
        or "<" in url
        or ">" in url
    ):
        return None
    if not _valid_source_url(url):
        return None
    return url


def _source_link(row: pd.Series) -> str:
    title = _escape_link_label(row.get("source_title"))
    url = _valid_url(row.get("source_url"))
    if url is None:
        return title
    return f"[{title}](<{url}>)"


def _coverage_table(coverage: dict[str, Any]) -> list[str]:
    labels = {
        "raw_assets": "原始资产",
        "consumer_universe": "消费候选池",
        "market_eligible": "市场条件合格",
        "oversold_eligible": "超跌条件合格",
        "hard_risk_clear": "硬风险通过",
        "evidence_complete": "证据完整",
        "valuation_eligible": "估值条件合格",
        "selected_expected": "纯预期修复入选",
        "selected_early": "初步验证入选",
    }
    lines = ["| 漏斗阶段 | 数量 |", "|---|---:|"]
    lines.extend(
        f"| {labels[key]} | {_escape_table(coverage['funnel'][key])} |" for key in _FUNNEL_KEYS
    )
    unified_labels = {
        "full": "完整评分池",
        "automatic": "自动门槛通过",
        "preaudit": "审计前候选",
        "evidence_reviewed": "证据已审阅",
        "evidence_complete": "证据完整（审计前）",
        "elasticity_complete": (
            "启动数据完整"
            if coverage.get("ranking_version") == "v2"
            else "弹性数据完整"
        ),
        "final": "最终榜单",
        "reserve": "储备榜单",
    }
    lines.extend(
        f"| {unified_labels[key]} | {_escape_table(coverage['unified_funnel'][key])} |"
        for key in _UNIFIED_FUNNEL_KEYS
    )
    for label, key in (
        ("估值历史覆盖", "valuation_history_coverage"),
        ("财务历史覆盖", "finance_history_coverage"),
    ):
        lines.append(f"| {label} | {_escape_table(json.dumps(coverage[key], ensure_ascii=False, sort_keys=True))} |")
    return lines


def _candidate_section(
    title: str,
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    for _, row in frame.iterrows():
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        score_detail = (
            (
                "- 启动评分：技术启动 "
                f"{_score_text(row.get('technical_readiness_score'))}；历史延续 "
                f"{_score_text(row.get('continuation_character_score'))}；剩余空间 "
                f"{_score_text(row.get('residual_price_space_score'))}；资金效率 "
                f"{_score_text(row.get('capital_efficiency_score'))}；催化时间 "
                f"{_score_text(row.get('catalyst_timing_score'))}；3—5日启动 "
                f"{_score_text(row.get('activation_score'))}"
            )
            if ranking_version == "v2"
            else (
                "- 弹性评分：残差偏离 "
                f"{_score_text(row.get('residual_deviation_score'))}；股票特性 "
                f"{_score_text(row.get('stock_character_score'))}；市场容量 "
                f"{_score_text(row.get('market_capacity_score'))}；催化流动性 "
                f"{_score_text(row.get('catalyst_liquidity_score'))}；反弹弹性 "
                f"{_score_text(row.get('elasticity_score'))}"
            )
        )
        lines.extend(
            [
                f"### {_escape_table(name)}（{_escape_table(code)}）",
                "",
                f"- 行业分类：{_escape_table(row.get('consumer_subindustry'))}",
                (
                    "- 跌幅：6个月 "
                    f"{_percent_text(row.get('return_6m'))}；12个月最大回撤 "
                    f"{_percent_text(row.get('max_drawdown_12m'))}；相对收益 "
                    f"{_percent_text(row.get('relative_return_6m'))}"
                ),
                (
                    f"- 估值：{_escape_table(row.get('valuation_method'))}；分位 "
                    f"{_percent_text(row.get('valuation_percentile'))}；三情景 "
                    f"{_percent_text(row.get('pessimistic_upside'))} / "
                    f"{_percent_text(row.get('base_upside'))} / "
                    f"{_percent_text(row.get('optimistic_upside'))}"
                ),
                f"- 修复逻辑：{_escape_table(row.get('repair_thesis'))}",
                f"- 未修复指标：{_escape_table(row.get('unrepaired_metrics'))}",
                f"- 领先指标：{_escape_table(row.get('leading_indicator'))}",
                f"- 下一验证日：{_escape_table(row.get('expected_validation_date'))}",
                f"- 来源：{_source_link(row)}（{_escape_table(row.get('source_publish_date'))}）",
                f"- 主要风险：{_escape_table(row.get('main_risks'))}",
                f"- 失效条件：{_escape_table(row.get('invalidation_conditions'))}",
                (
                    "- 评分：经营缺口 "
                    f"{_escape_table(row.get('operating_gap_score'))}；修复潜力 "
                    f"{_escape_table(row.get('repair_potential_score'))}；估值修复 "
                    f"{_escape_table(row.get('valuation_repair_score'))}；超跌 "
                    f"{_escape_table(row.get('oversold_score'))}；资产负债表 "
                    f"{_escape_table(row.get('balance_sheet_score'))}；催化可验证性 "
                    f"{_escape_table(row.get('catalyst_verifiability_score'))}；已定价扣分 "
                    f"{_escape_table(row.get('priced_in_penalty'))}；综合分 "
                    f"{_escape_table(row.get('composite_score'))}"
                ),
                (
                    "- 真实市值：总市值 "
                    f"{_market_cap_text(row.get('current_total_market_cap'))}；流通市值 "
                    f"{_market_cap_text(row.get('current_float_market_cap'))}；来源 "
                    f"{_escape_table(row.get('market_cap_source'))}"
                ),
                (
                    "- 大涨特征：涨停 "
                    f"{_count_text(row.get('limit_up_count_2y'))} 次；上涨超过7% "
                    f"{_count_text(row.get('up_7pct_count_2y'))} 次；上涨超过5% "
                    f"{_count_text(row.get('up_5pct_count_2y'))} 次；大涨后正收益率 "
                    f"1日 {_percent_text(row.get('positive_after_big_up_1d_rate'))}；"
                    f"3日 {_percent_text(row.get('positive_after_big_up_3d_rate'))}；"
                    f"5日 {_percent_text(row.get('positive_after_big_up_5d_rate'))}"
                ),
                (
                    "- 位置与反弹：1年回撤 "
                    f"{_percent_text(row.get('drawdown_from_high_1y'))}；2年回撤 "
                    f"{_percent_text(row.get('drawdown_from_high_2y'))}；1年位置 "
                    f"{_percent_text(row.get('price_position_1y'))}；2年位置 "
                    f"{_percent_text(row.get('price_position_2y'))}；MA120 "
                    f"{_percent_text(row.get('distance_hfq_ma120'))}；MA250 "
                    f"{_percent_text(row.get('distance_hfq_ma250'))}；60日反弹 "
                    f"{_percent_text(row.get('rebound_from_low_60d'))}；120日反弹 "
                    f"{_percent_text(row.get('rebound_from_low_120d'))}"
                ),
                score_detail,
                "",
            ]
        )
    return lines


def _exclusion_summary(frame: pd.DataFrame) -> list[str]:
    lines = ["## 剔除原因摘要", ""]
    if frame.empty or "exclusion_reasons" not in frame.columns:
        return [*lines, "暂无剔除记录。", ""]
    reasons: list[str] = []
    for value in frame["exclusion_reasons"].dropna():
        reasons.extend(part.strip() for part in str(value).split("|") if part.strip())
    if not reasons:
        return [*lines, "暂无可统计的剔除原因。", ""]
    counts = pd.Series(reasons).value_counts(sort=False).sort_index()
    lines.extend(["| 原因 | 数量 |", "|---|---:|"])
    lines.extend(f"| {_escape_table(reason)} | {count} |" for reason, count in counts.items())
    return [*lines, ""]


def _ranking_table(
    title: str,
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    score_label = "启动分位" if ranking_version == "v2" else "弹性分位"
    score_field = (
        "activation_rank_percentile"
        if ranking_version == "v2"
        else "elasticity_rank_percentile"
    )
    final_field = (
        "final_rank_score_v2" if ranking_version == "v2" else "final_rank_score"
    )
    lines.extend(
        [
            f"| 排名 | 股票 | 修复分位 | {score_label} | 最终排名分 |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for _, row in frame.iterrows():
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        lines.append(
            f"| {_escape_table(row.get('final_rank'))} | "
            f"{_escape_table(name)}（{_escape_table(code)}） | "
            f"{_score_text(row.get('repair_rank_percentile'))} | "
            f"{_score_text(row.get(score_field))} | "
            f"{_score_text(row.get(final_field))} |"
        )
    return [*lines, ""]


def _preaudit_table(
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    lines = ["## 审计前 Top 60", ""]
    if frame.empty:
        return [*lines, "暂无候选。", ""]
    score_label = "3—5日启动分" if ranking_version == "v2" else "自动弹性分"
    score_field = (
        "activation_score" if ranking_version == "v2" else "automatic_elasticity_score"
    )
    lines.extend(
        [
            f"| 预审排名 | 股票 | 预审分 | 修复潜力 | {score_label} | 证据状态 |",
            "|---:|---|---:|---:|---:|---|",
        ]
    )
    for preaudit_rank, (_, row) in enumerate(frame.iterrows(), start=1):
        name = _display(row.get("stock_name"))
        code = _display(row.get("stock_code", row.get("asset_id")))
        evidence_complete = row.get("evidence_complete")
        evidence_status = (
            "证据完整"
            if isinstance(evidence_complete, (bool, np.bool_))
            and bool(evidence_complete)
            else "证据不完整"
        )
        lines.append(
            f"| {preaudit_rank} | {_escape_table(name)}（{_escape_table(code)}） | "
            f"{_score_text(row.get('preaudit_score'))} | "
            f"{_score_text(row.get('repair_potential_score'))} | "
            f"{_score_text(row.get(score_field))} | "
            f"{evidence_status} |"
        )
    return [*lines, ""]


def _comparison_table(
    frame: pd.DataFrame,
    *,
    ranking_version: str = "v1",
) -> list[str]:
    title = "V1/V2 排名变动" if ranking_version == "v2" else "新旧排名对照"
    lines = [f"## {title}", ""]
    if frame.empty:
        return [*lines, "暂无对照记录。", ""]
    rank_labels = (
        "| 股票 | V1 排名 | V2 排名 | 变化 |"
        if ranking_version == "v2"
        else "| 股票 | 旧排名 | 新排名 | 变化 |"
    )
    lines.extend([rank_labels, "|---|---:|---:|---:|"])
    for _, row in frame.iterrows():
        old_rank = row.get(
            "old_combined_rank", row.get("old_rank", row.get("v1_rank"))
        )
        lines.append(
            f"| {_escape_table(row.get('stock_name', row.get('asset_id')))} | "
            f"{_escape_table(old_rank)} | "
            f"{_escape_table(row.get('new_rank', row.get('v2_rank')))} | "
            f"{_escape_table(row.get('rank_change'))} |"
        )
    return [*lines, ""]


def _v2_segment_table(top30: pd.DataFrame) -> list[str]:
    lines = ["## Top30 分段", "", "| 分段 | 实际数量 |", "|---|---:|"]
    for label, start, end in (
        ("1—10", 1, 10),
        ("11—20", 11, 20),
        ("21—30", 21, 30),
    ):
        if top30.empty or "final_rank" not in top30.columns:
            count = 0
        else:
            ranks = pd.to_numeric(top30["final_rank"], errors="coerce")
            count = int(ranks.between(start, end, inclusive="both").sum())
        lines.append(f"| {label} | {count} |")
    return [*lines, ""]


def _v2_second_gate_exclusion_summary(frame: pd.DataFrame) -> list[str]:
    lines = ["## 第二门槛排除原因", ""]
    if frame.empty:
        return [*lines, "暂无第二门槛剔除记录。", ""]
    if "exclusion_stage" in frame.columns:
        selected = frame.loc[frame["exclusion_stage"].astype(str).eq("activation")]
    else:
        selected = frame.iloc[0:0]
    reason_field = (
        "activation_exclusion_reasons"
        if "activation_exclusion_reasons" in selected.columns
        else "exclusion_reasons"
    )
    if selected.empty or reason_field not in selected.columns:
        return [*lines, "暂无第二门槛剔除记录。", ""]
    reasons: list[str] = []
    for value in selected[reason_field].dropna():
        reasons.extend(part.strip() for part in str(value).split("|") if part.strip())
    if not reasons:
        return [*lines, "暂无第二门槛剔除记录。", ""]
    counts = pd.Series(reasons).value_counts(sort=False).sort_index()
    lines.extend(["| 原因 | 数量 |", "|---|---:|"])
    lines.extend(
        f"| {_escape_table(reason)} | {int(count)} |"
        for reason, count in counts.items()
    )
    return [*lines, ""]


def _weight_percent(mapping: dict[str, Any], key: str) -> str:
    value = float(mapping[key]) * 100.0
    rounded = round(value)
    return f"{rounded:.0f}%" if math.isclose(value, rounded, abs_tol=1e-12) else f"{value:.1f}%"


_FIXED_SPECIAL_STOCKS = (
    ("600418", "江淮汽车"),
    ("600702", "舍得酒业"),
    ("601127", "赛力斯"),
)


def _meaningful(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return not isinstance(value, str) or bool(value.strip())


def _find_special_stock(frame: pd.DataFrame, code: str, name: str) -> pd.Series | None:
    if frame.empty:
        return None
    matched = pd.Series(False, index=frame.index)
    if "stock_code" in frame.columns:
        matched |= frame["stock_code"].astype(str).str.split(".").str[0].eq(code)
    if "asset_id" in frame.columns:
        matched |= frame["asset_id"].astype(str).str.split(".").str[0].eq(code)
    if "stock_name" in frame.columns:
        matched |= frame["stock_name"].astype(str).str.strip().eq(name)
    if not matched.any():
        return None
    return frame.loc[matched].iloc[0]


def _special_stock_comparison(
    comparison: pd.DataFrame,
    scores: pd.DataFrame | None,
    top20: pd.DataFrame,
    reserve: pd.DataFrame,
    preaudit: pd.DataFrame,
) -> list[str]:
    lines = ["## 江淮汽车、舍得酒业、赛力斯对照", ""]
    sources = (comparison, scores, top20, reserve, preaudit)
    for code, name in _FIXED_SPECIAL_STOCKS:
        combined: dict[str, Any] = {}
        found = False
        in_preaudit = _find_special_stock(preaudit, code, name) is not None
        for source in sources:
            if source is None:
                continue
            row = _find_special_stock(source, code, name)
            if row is None:
                continue
            found = True
            for field, value in row.items():
                if field not in combined and _meaningful(value):
                    combined[field] = value
        lines.extend([f"### {name}（{code}）", ""])
        lines.append(
            "- 审计状态：已进入本期终端消费审计。"
            if in_preaudit
            else "- 审计状态：未进入本期终端消费审计。"
        )
        if not found:
            lines.extend(["- 无可用排名。", ""])
            continue
        old_rank = combined.get(
            "old_combined_rank", combined.get("old_rank", combined.get("v1_rank"))
        )
        new_rank = combined.get(
            "new_rank", combined.get("v2_rank", combined.get("final_rank"))
        )
        rank_change = combined.get("rank_change")
        rank_parts = []
        if _meaningful(old_rank):
            rank_parts.append(f"旧排名 {_count_text(old_rank)}")
        if _meaningful(new_rank):
            rank_parts.append(f"新排名 {_count_text(new_rank)}")
        if _meaningful(rank_change):
            rank_parts.append(f"排名变化 {_count_text(rank_change)}")
        lines.append(f"- {'；'.join(rank_parts)}" if rank_parts else "- 无可用排名。")
        reasons = combined.get(
            "exclusion_reasons", combined.get("automatic_exclusion_reasons")
        )
        if _meaningful(reasons):
            lines.append(f"- 状态/剔除原因：{_escape_table(reasons)}")
        else:
            lines.append("- 状态/剔除原因：无明确剔除原因。")
        lines.append("")
    return lines


def _render_report(
    trade_date: str,
    top20: pd.DataFrame,
    reserve: pd.DataFrame,
    preaudit: pd.DataFrame,
    comparison: pd.DataFrame,
    exclusions: pd.DataFrame,
    coverage: dict[str, Any],
    scores: pd.DataFrame | None = None,
    *,
    top30: pd.DataFrame | None = None,
    ranked_pool: pd.DataFrame | None = None,
) -> str:
    ranking_version = str(coverage.get("ranking_version", "v1"))
    if ranking_version == "v2":
        top30_frame = (
            top30.copy(deep=True)
            if top30 is not None
            else pd.concat([top20, reserve], ignore_index=True).loc[
                lambda frame: pd.to_numeric(
                    frame.get(
                        "final_rank", pd.Series(index=frame.index, dtype="float64")
                    ),
                    errors="coerce",
                ).le(30)
            ]
        )
        ranked_pool_count = (
            len(ranked_pool)
            if ranked_pool is not None
            else int(coverage.get("v2_ranked_pool_count", len(top20) + len(reserve)))
        )
    else:
        top30_frame = pd.DataFrame()
        ranked_pool_count = 0
    candidate_details = _enrich_rows(
        pd.concat([top20, reserve], ignore_index=True), scores
    )
    rank_weights = coverage.get(
        "v2_rank_weights", {"repair": 0.55, "activation": 0.45}
    )
    activation_weights = coverage.get(
        "v2_activation_weights",
        {
            "technical_readiness": 0.30,
            "continuation_character": 0.25,
            "residual_price_space": 0.20,
            "capital_efficiency": 0.15,
            "catalyst_timing": 0.10,
        },
    )
    methodology_lines = (
        [
            (
                "> 单一排名公式：修复潜力 "
                f"{_weight_percent(rank_weights, 'repair')} + 3—5日启动 "
                f"{_weight_percent(rank_weights, 'activation')}。"
            ),
            "",
            (
                "> 3—5日启动分：技术启动 "
                f"{_weight_percent(activation_weights, 'technical_readiness')} + "
                "历史延续 "
                f"{_weight_percent(activation_weights, 'continuation_character')} + "
                "剩余价格空间 "
                f"{_weight_percent(activation_weights, 'residual_price_space')} + "
                "资金推动效率 "
                f"{_weight_percent(activation_weights, 'capital_efficiency')} + "
                "催化时间 "
                f"{_weight_percent(activation_weights, 'catalyst_timing')}。"
            ),
        ]
        if ranking_version == "v2"
        else ["> 单一排名公式：修复潜力 70% + 反弹弹性 30%。"]
    )
    lines = [
        f"# 消费超跌修复候选周报（{trade_date}）",
        "",
        "> 方法声明：本报告仅提供研究候选，不是交易指令。",
        "",
        "> CSV 为审阅安全转义：疑似公式的文本单元格已加单引号前缀。",
        "",
        *(
            [
                "> 排名版本：v2",
                "",
                "> 本期排名完全由冻结数据和统一规则生成，未进行任何人工调序。",
                "",
                f"> 数据截止日：{trade_date}",
                "",
            ]
            if ranking_version == "v2"
            else []
        ),
        *methodology_lines,
        "",
        f"> 发布状态：{_escape_table(coverage['publication_status'])}",
        "",
        *(
            [
                f"> 通过两道门槛后实际发布 {ranked_pool_count} 只，门槛未因数量不足而放宽。",
                "",
            ]
            if ranking_version == "v2"
            else []
        ),
        *(
            ["> **仅预审，不是正式Top20。**", ""]
            if coverage["publication_status"] == "preaudit_only"
            else []
        ),
        "## 数据覆盖",
        "",
        *_coverage_table(coverage),
        "",
        "### 数据日期上限与缺失字段",
        "",
        f"- 数据日期上限：{_escape_table(json.dumps(coverage['data_date_maxima'], ensure_ascii=False, sort_keys=True))}",
        f"- 缺失字段计数：{_escape_table(json.dumps(coverage['missing_field_counts'], ensure_ascii=False, sort_keys=True))}",
        "",
        *(
            [
                "### V2 双门槛",
                "",
                (
                    "- 第一门槛通过："
                    f"{_escape_table(coverage.get('activation_funnel', {}).get('first_gate_eligible'))}"
                ),
                (
                    "- 启动数据完整："
                    f"{_escape_table(coverage.get('activation_funnel', {}).get('activation_covered'))}"
                ),
                (
                    "- 第二门槛通过："
                    f"{_escape_table(coverage.get('activation_funnel', {}).get('activation_eligible'))}"
                ),
                f"- 最终合格池：{ranked_pool_count}",
                "",
            ]
            if ranking_version == "v2"
            else []
        ),
        *_ranking_table(
            "最终统一榜单 Top 20", top20, ranking_version=ranking_version
        ),
        *(
            _ranking_table(
                "Top 21—30",
                top30_frame.loc[
                    pd.to_numeric(top30_frame["final_rank"], errors="coerce").between(
                        21, 30, inclusive="both"
                    )
                ]
                if "final_rank" in top30_frame.columns
                else top30_frame.iloc[0:0],
                ranking_version="v2",
            )
            if ranking_version == "v2"
            else []
        ),
        *(_v2_segment_table(top30_frame) if ranking_version == "v2" else []),
        *_ranking_table(
            "储备榜单 21-40", reserve, ranking_version=ranking_version
        ),
        *_preaudit_table(preaudit, ranking_version=ranking_version),
        *_comparison_table(comparison, ranking_version=ranking_version),
        *_candidate_section(
            "候选详情", candidate_details, ranking_version=ranking_version
        ),
        *_special_stock_comparison(comparison, scores, top20, reserve, preaudit),
        *(
            _v2_second_gate_exclusion_summary(exclusions)
            if ranking_version == "v2"
            else []
        ),
        *_exclusion_summary(exclusions),
        "## 警告",
        "",
    ]
    warnings = coverage["warnings"]
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {_escape_table(warning)}" for warning in warnings)
    else:
        lines.append("- 无")
    return "\n".join(lines).rstrip() + "\n"


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        path.chmod(0o755)
        shutil.rmtree(path)


def _cleanup_stale(output_dir: Path, releases_dir: Path) -> None:
    for path in releases_dir.glob(f"{_STAGING_PREFIX}*"):
        _remove_path(path)
    for path in output_dir.glob(f"{_TEMP_LINK_PREFIX}*"):
        _remove_path(path)


def _restore_current(output_dir: Path, old_target: str | None) -> None:
    current = output_dir / "current"
    if old_target is None:
        current.unlink(missing_ok=True)
        return
    recovery = output_dir / f"{_TEMP_LINK_PREFIX}recovery-{uuid.uuid4().hex}"
    try:
        os.symlink(old_target, recovery)
        os.replace(recovery, current)
    finally:
        recovery.unlink(missing_ok=True)


def _open_directory_no_follow(path: Path, name: str) -> int:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o755)
        except FileExistsError:
            pass
        metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{name} must be a real directory, not a symlink")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{name} must be a real directory, not a symlink") from exc
    opened = os.fstat(descriptor)
    current = os.lstat(path)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        os.close(descriptor)
        raise ValueError(f"{name} changed during validation")
    return descriptor


def _verify_directory_identity(path: Path, descriptor: int, name: str) -> None:
    opened = os.fstat(descriptor)
    current = os.lstat(path)
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise ValueError(f"{name} changed during publication")


def _validated_current_target(
    current: Path, output_dir: Path, releases_dir: Path
) -> str | None:
    if not current.is_symlink():
        if current.exists():
            raise ValueError("output_dir/current must be a symlink managed by this publisher")
        return None
    target = os.readlink(current)
    pure_target = PurePath(target)
    parts = pure_target.parts
    if (
        pure_target.is_absolute()
        or len(parts) != 2
        or parts[0] != ".releases"
        or not parts[1].startswith(_RELEASE_PREFIX)
        or parts[1] == _RELEASE_PREFIX
        or ".." in parts
    ):
        raise ValueError("output_dir/current target is not a managed relative release")
    release = output_dir.joinpath(*parts)
    try:
        metadata = os.lstat(release)
        resolved_release = release.resolve(strict=True)
        resolved_releases = releases_dir.resolve(strict=True)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise ValueError("output_dir/current target must be an existing managed release") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved_release.parent != resolved_releases
    ):
        raise ValueError("output_dir/current target must be a real managed release directory")
    return target


def _open_publish_lock(path: Path):
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError("output_dir/.publish.lock must be a regular file, not a symlink") from exc
    try:
        opened = os.fstat(descriptor)
        current = os.lstat(path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError("output_dir/.publish.lock must be a regular file, not a symlink")
        return os.fdopen(descriptor, "a+b")
    except BaseException:
        os.close(descriptor)
        raise


def _artifact_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_and_verify_manifest(
    release: Path,
    filenames: dict[str, str],
) -> Path:
    manifest = release / ".manifest.sha256"
    lines = [
        f"{_artifact_digest(release / filename)}  {filename}"
        for filename in sorted(filenames.values())
    ]
    _write_text("\n".join(lines) + "\n", manifest)
    parsed: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", 1)
        parsed[filename] = digest
    expected_names = sorted(filenames.values())
    if list(parsed) != expected_names or any(
        parsed[filename] != _artifact_digest(release / filename) for filename in expected_names
    ):
        raise ValueError("release manifest verification failed")
    return manifest


def _seal_release(
    release: Path,
    manifest: Path,
    filenames: dict[str, str],
) -> None:
    for filename in (*filenames.values(), manifest.name):
        artifact = release / filename
        artifact.chmod(0o444)
        _fsync_file(artifact)
    release.chmod(0o555)
    _dir_fsync(release)


def _publish_release(
    output_dir: Path,
    frames: dict[str, pd.DataFrame],
    coverage: dict[str, Any],
    report: str,
    filenames: dict[str, str] = UNIFIED_OUTPUT_FILENAMES,
) -> None:
    releases_dir = output_dir / ".releases"
    releases_descriptor = _open_directory_no_follow(
        releases_dir, "output_dir/.releases"
    )
    try:
        _verify_directory_identity(
            releases_dir, releases_descriptor, "output_dir/.releases"
        )
        current = output_dir / "current"
        old_target = _validated_current_target(current, output_dir, releases_dir)
        _cleanup_stale(output_dir, releases_dir)
        identifier = uuid.uuid4().hex
        staging = releases_dir / f"{_STAGING_PREFIX}{identifier}"
        release = releases_dir / f"{_RELEASE_PREFIX}{identifier}"
        temp_link = output_dir / f"{_TEMP_LINK_PREFIX}{identifier}"
        switched = False
        preserve_release = False
        staging.mkdir()
        try:
            frame_keys = tuple(
                key for key in filenames if key not in {"coverage", "report"}
            )
            for key in frame_keys:
                _write_csv(frames[key], staging / filenames[key])
            _write_text(
                json.dumps(
                    coverage, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
                )
                + "\n",
                staging / filenames["coverage"],
            )
            _write_text(report, staging / filenames["report"])
            manifest = _write_and_verify_manifest(staging, filenames)
            _seal_release(staging, manifest, filenames)
            _verify_directory_identity(
                releases_dir, releases_descriptor, "output_dir/.releases"
            )
            os.replace(staging, release)
            _dir_fsync(releases_dir)
            relative_target = str(Path(".releases") / release.name)
            os.symlink(relative_target, temp_link)
            _dir_fsync(output_dir)
            os.replace(temp_link, current)
            switched = True
            try:
                _dir_fsync(output_dir)
            except OSError as publication_error:
                try:
                    _restore_current(output_dir, old_target)
                    _dir_fsync(output_dir)
                except BaseException as rollback_error:
                    preserve_release = True
                    failure = RuntimeError(
                        f"artifact publication failed and rollback incomplete: {rollback_error}"
                    )
                    raise failure from publication_error
                switched = False
                raise
        finally:
            _remove_path(staging)
            temp_link.unlink(missing_ok=True)
            if not switched and not preserve_release:
                _remove_path(release)
    finally:
        os.close(releases_descriptor)


def write_consumer_oversold_artifacts(
    payload: dict[str, Any], *, output_dir: str | Path
) -> dict[str, Any]:
    """Validate, render, and atomically publish consumer oversold research artifacts."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if not isinstance(payload.get("coverage"), dict):
        if "coverage" not in payload:
            raise ValueError("payload missing required keys: coverage")
        raise TypeError("coverage must be a dict")
    ranking_version = payload["coverage"].get("ranking_version", "v1")
    if ranking_version not in {"v1", "v2"}:
        raise ValueError("coverage ranking_version must be v1 or v2")
    payload_keys = _V2_PAYLOAD_KEYS if ranking_version == "v2" else _PAYLOAD_KEYS
    frame_keys = _V2_FRAME_KEYS if ranking_version == "v2" else _FRAME_KEYS
    filenames = (
        V2_OUTPUT_FILENAMES if ranking_version == "v2" else UNIFIED_OUTPUT_FILENAMES
    )
    missing = _missing_keys(payload, payload_keys)
    if missing:
        raise ValueError(f"payload missing required keys: {', '.join(missing)}")
    trade_date = validate_trade_date(payload["trade_date"])
    frames: dict[str, pd.DataFrame] = {}
    raw_frames: dict[str, pd.DataFrame] = {}
    for key in frame_keys:
        frame = payload[key]
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{key} must be a pandas DataFrame")
        raw_frames[key] = frame.copy(deep=True)
        frames[key] = _ordered_evidence_frame(frame) if key == "evidence" else _ordered_frame(frame)
    if ranking_version == "v2":
        coverage_trade_date = payload["coverage"].get("trade_date")
        if coverage_trade_date is not None and coverage_trade_date != trade_date:
            raise ValueError("coverage trade_date must match payload trade_date")
        for key in ("evidence", "scores", "exclusions"):
            _validate_assets(raw_frames[key], key)
        frame_counts = _validate_v2_frames(raw_frames, payload["coverage"])
        coverage = _normalize_v2_coverage(
            payload["coverage"], trade_date, frame_counts=frame_counts
        )
        report = _render_report(
            trade_date,
            frames["top20"],
            frames["reserve"],
            frames["preaudit"],
            frames["comparison"],
            frames["exclusions"],
            coverage,
            frames["scores"],
            top30=frames["top30"],
            ranked_pool=frames["ranked_pool"],
        )
    else:
        _, preaudit_assets = _validate_assets(frames["preaudit"], "preaudit")
        _validate_assets(frames["comparison"], "comparison")
        coverage = _normalize_coverage(
            payload["coverage"],
            trade_date,
            top20_count=len(frames["top20"]),
            reserve_count=len(frames["reserve"]),
            preaudit_count=len(frames["preaudit"]),
        )
        final_top_n = coverage["final_top_n"]
        top20_assets = _validate_selected(
            frames["top20"], "top20", range(1, len(frames["top20"]) + 1)
        )
        reserve_assets = _validate_selected(
            frames["reserve"],
            "reserve",
            range(final_top_n + 1, final_top_n + len(frames["reserve"]) + 1),
        )
        if top20_assets & reserve_assets:
            raise ValueError("top20 and reserve asset sets must be mutually exclusive")
        if not (top20_assets | reserve_assets).issubset(preaudit_assets):
            raise ValueError("top20 and reserve assets must be present in preaudit")
        report = _render_report(
            trade_date,
            frames["top20"],
            frames["reserve"],
            frames["preaudit"],
            frames["comparison"],
            frames["exclusions"],
            coverage,
            frames["scores"],
        )

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    lock_path = destination / ".publish.lock"
    lock_handle = _open_publish_lock(lock_path)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        _publish_release(
            destination,
            frames,
            coverage,
            report,
            filenames=filenames,
        )
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()

    paths = {
        key: str(destination / "current" / filename)
        for key, filename in filenames.items()
    }
    return {
        "paths": paths,
        **frames,
        "coverage": coverage,
        "report": report,
    }
