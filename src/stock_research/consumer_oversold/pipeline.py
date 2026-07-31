from __future__ import annotations

import copy
import fcntl
import math
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS

from .activation import (
    compute_technical_readiness_features,
    score_activation_candidates,
)
from .contracts import (
    UNIFIED_OUTPUT_FILENAMES,
    ConsumerOversoldConfig,
    validate_trade_date,
)
from .evidence import EVIDENCE_COLUMNS, validate_repair_evidence
from .elasticity import (
    MARKET_CAPACITY_SHARE_COLUMNS,
    compute_market_capacity_features,
    compute_residual_price_features,
    compute_stock_character_features,
    score_rebound_elasticity,
)
from .features import (
    BAR_COLUMNS,
    CURRENT_VALUATION_COLUMNS,
    FINANCE_COLUMNS as FEATURE_FINANCE_COLUMNS,
    VALUATION_HISTORY_COLUMNS,
    compute_already_priced_features,
    compute_fundamental_features,
    compute_hard_risk_features,
    compute_oversold_score,
    compute_price_features,
    compute_valuation_features,
)
from .loaders import (
    load_consumer_finance_history,
    load_consumer_market_history,
    load_consumer_share_capacity,
    load_consumer_universe_frames,
    load_consumer_valuation_history,
)
from .reporting import (
    _json_safe,
    _open_publish_lock,
    _ordered_evidence_frame,
    _ordered_frame,
    _publish_release,
    _render_report,
    write_consumer_oversold_artifacts,
)
from .scoring import (
    apply_candidate_gates,
    rank_candidate_buckets,
    rank_unified_candidates,
    rank_v2_candidates,
    score_candidates,
)
from .universe import build_consumer_universe_from_frames


INDUSTRY_RULES_PATH = SETTINGS.repo_root / "config" / "consumer_oversold_industry_rules_v1.csv"
ASSET_OVERRIDES_PATH = SETTINGS.repo_root / "config" / "consumer_oversold_asset_overrides_v1.csv"
RETROSPECTIVE_EVIDENCE_TRADE_DATE = "2026-07-27"
RETROSPECTIVE_EVIDENCE_PUBLICATION_FIELDS = (
    "source_publish_date",
    "audit_review_source_publish_date",
    "pledge_debt_review_source_publish_date",
    "permanent_impairment_source_publish_date",
)


def validate_retrospective_evidence_publications(
    evidence: pd.DataFrame,
    *,
    ranking_version: str,
    trade_date: str,
    reconstruction_mode: str,
    information_cutoff: str,
) -> dict[str, str]:
    """Validate the underlying publication dates before retrospective sealing."""
    if ranking_version != "v2":
        raise ValueError("retrospective evidence reconstruction requires ranking_version v2")
    normalized_trade_date = validate_trade_date(trade_date)
    if normalized_trade_date != RETROSPECTIVE_EVIDENCE_TRADE_DATE:
        raise ValueError(
            "retrospective evidence reconstruction is only supported for 2026-07-27"
        )
    if reconstruction_mode != "retrospective_point_in_time":
        raise ValueError(
            "evidence_reconstruction_mode must be retrospective_point_in_time"
        )
    cutoff = validate_trade_date(information_cutoff)
    if cutoff != normalized_trade_date:
        raise ValueError("evidence_information_cutoff must equal trade_date")
    if not isinstance(evidence, pd.DataFrame):
        raise TypeError("evidence must be a pandas DataFrame")
    missing_fields = [
        field
        for field in RETROSPECTIVE_EVIDENCE_PUBLICATION_FIELDS
        if field not in evidence.columns
    ]
    if missing_fields:
        raise ValueError(
            "retrospective evidence missing publication fields: "
            + ", ".join(missing_fields)
        )
    for row_number, row in enumerate(evidence.to_dict(orient="records"), start=2):
        raw_asset_id = row.get("asset_id", "")
        asset_id = (
            ""
            if pd.isna(raw_asset_id)
            else str(raw_asset_id).strip()
        ) or f"row {row_number}"
        for field in RETROSPECTIVE_EVIDENCE_PUBLICATION_FIELDS:
            raw_value = row.get(field)
            value = "" if pd.isna(raw_value) else str(raw_value).strip()
            if not value:
                raise ValueError(
                    f"missing evidence publication for {asset_id}: {field}"
                )
            try:
                published = validate_trade_date(value)
            except ValueError as exc:
                raise ValueError(
                    f"retrospective evidence {field} must use YYYY-MM-DD for {asset_id}"
                ) from exc
            if published > cutoff:
                raise ValueError(
                    "future evidence publication "
                    f"for {asset_id}: {field}={published} exceeds {cutoff}"
                )
    return {
        "evidence_reconstruction_mode": reconstruction_mode,
        "evidence_information_cutoff": cutoff,
    }

REQUIRED_FRAME_KEYS = (
    "assets",
    "statuses",
    "liquidity",
    "industries",
    "industry_rules",
    "asset_overrides",
    "bars",
    "share_capacity",
    "finance",
    "current_valuation",
    "valuation_history",
)

EXCLUSION_ID_COLUMNS = (
    "asset_id",
    "stock_code",
    "stock_name",
    "consumer_subindustry",
    "exclusion_stage",
    "exclusion_reasons",
)
COMPARISON_COLUMNS = [
    "asset_id",
    "stock_code",
    "stock_name",
    "repair_bucket",
    "old_bucket_rank",
    "old_combined_rank",
    "new_rank",
    "rank_change",
    "composite_score",
    "elasticity_score",
    "final_rank_score",
    "exclusion_reasons",
]
UNIFIED_OUTPUT_COLUMNS = [
    "asset_id",
    "stock_code",
    "stock_name",
    "consumer_subindustry",
    "repair_bucket",
    "final_rank",
    "final_rank_score",
    "repair_rank_percentile",
    "elasticity_rank_percentile",
    "composite_score",
    "elasticity_score",
    "repair_potential_score",
    "valuation_repair_score",
    "operating_gap_score",
    "balance_sheet_score",
    "oversold_score",
    "base_upside",
    "current_total_market_cap",
    "current_float_market_cap",
    "market_cap_source",
    "pessimistic_scenario_market_cap",
    "base_scenario_market_cap",
    "optimistic_scenario_market_cap",
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "drawdown_from_high_1y",
    "drawdown_from_high_2y",
    "price_position_1y",
    "price_position_2y",
    "distance_hfq_ma120",
    "distance_hfq_ma250",
    "rebound_from_low_60d",
    "rebound_from_low_120d",
    "return_6m",
    "relative_return_6m",
    "valuation_percentile",
    "residual_deviation_score",
    "stock_character_score",
    "market_capacity_score",
    "catalyst_liquidity_score",
    "evidence_complete",
    "repair_thesis",
    "unrepaired_metrics",
    "leading_indicator",
    "expected_validation_date",
    "source_title",
    "source_url",
    "source_publish_date",
    "main_risks",
    "invalidation_conditions",
    "audit_review_status",
    "pledge_debt_review_status",
    "permanent_impairment_status",
    "eligible",
    "automatic_eligible",
    "elasticity_coverage",
    "automatic_elasticity_coverage",
    "residual_deviation_component_coverage",
    "stock_character_component_coverage",
    "market_capacity_component_coverage",
    "catalyst_liquidity_coverage",
    "exclusion_reasons",
    "automatic_exclusion_reasons",
]
PREAUDIT_OUTPUT_COLUMNS = [
    *UNIFIED_OUTPUT_COLUMNS,
    "preaudit_score",
    "automatic_elasticity_score",
    "evidence_errors",
]
V2_OUTPUT_COLUMNS = [
    *UNIFIED_OUTPUT_COLUMNS,
    "trade_date",
    "ranking_version",
    "final_rank_score_v2",
    "activation_rank_percentile",
    "activation_score",
    "technical_readiness_score",
    "continuation_character_score",
    "residual_price_space_score",
    "capital_efficiency_score",
    "catalyst_timing_score",
    "activation_coverage",
    "activation_eligible",
    "activation_exclusion_reasons",
    "falling_knife",
    "overextended",
]
V2_PREAUDIT_OUTPUT_COLUMNS = [
    *V2_OUTPUT_COLUMNS,
    "preaudit_score",
    "automatic_elasticity_score",
    "evidence_errors",
]
V2_COMPARISON_COLUMNS = [
    "asset_id",
    "stock_code",
    "stock_name",
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
]
V2_COMPATIBILITY_PUBLICATION_FRAME_KEYS = (
    "evidence",
    "scores",
    "exclusions",
    "top20",
    "reserve",
    "preaudit",
    "comparison",
)


def _empty_unified_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIFIED_OUTPUT_COLUMNS)


def _empty_v2_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=V2_OUTPUT_COLUMNS)


def _validated_v2_assets(frame: pd.DataFrame, name: str) -> list[str]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if "asset_id" not in frame.columns:
        raise ValueError(f"{name} missing required columns: asset_id")
    if frame.empty:
        return []
    missing = frame["asset_id"].isna()
    normalized = frame["asset_id"].astype(str).str.strip()
    if (missing | normalized.eq("")).any():
        raise ValueError(f"{name} asset_id must be non-empty")
    duplicate = normalized.duplicated(keep=False)
    if duplicate.any():
        asset_id = normalized.loc[duplicate].sort_values(kind="stable").iloc[0]
        raise ValueError(f"{name} contains duplicate asset_id {asset_id}")
    return normalized.tolist()


def _validate_v2_rank_frame(
    frame: pd.DataFrame,
    name: str,
    *,
    start_rank: int,
) -> list[str]:
    asset_ids = _validated_v2_assets(frame, name)
    required = (
        "final_rank",
        "eligible",
        "activation_coverage",
        "activation_eligible",
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")
    ranks: list[int] = []
    for value in frame["final_rank"]:
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)
        ):
            raise ValueError(f"{name} final_rank must contain strict integers")
        ranks.append(int(value))
    expected = list(range(start_rank, start_rank + len(frame)))
    if ranks != expected:
        raise ValueError(f"{name} final_rank must be continuous from {start_rank}")
    for field in ("eligible", "activation_coverage", "activation_eligible"):
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
    shared_columns = [
        column for column in selection.columns if column in ranked_slice.columns
    ]
    if not shared_columns:
        raise ValueError(f"{name} has no shared columns with ranked_pool")
    try:
        pd.testing.assert_frame_equal(
            selection.loc[:, shared_columns].reset_index(drop=True),
            ranked_slice.loc[:, shared_columns].reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError(
            f"{name} must equal ranked_pool slice across shared columns"
        ) from exc


def _validate_v2_compatibility_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    required_keys = (
        "trade_date",
        "evidence",
        "scores",
        "exclusions",
        "coverage",
        "top20",
        "top30",
        "reserve",
        "ranked_pool",
        "preaudit",
        "comparison",
    )
    missing_keys = [key for key in required_keys if key not in payload]
    if missing_keys:
        raise ValueError(f"payload missing required keys: {', '.join(missing_keys)}")
    validate_trade_date(payload["trade_date"])
    coverage = payload["coverage"]
    if not isinstance(coverage, dict):
        raise TypeError("coverage must be a dict")
    if coverage.get("ranking_version") != "v2":
        raise ValueError("coverage ranking_version must be v2")
    coverage_trade_date = coverage.get("trade_date")
    if coverage_trade_date is not None and coverage_trade_date != payload["trade_date"]:
        raise ValueError("coverage trade_date must match payload trade_date")

    for name in ("evidence", "scores", "exclusions", "preaudit", "comparison"):
        _validated_v2_assets(payload[name], name)
    ranked_ids = _validate_v2_rank_frame(
        payload["ranked_pool"], "ranked_pool", start_rank=1
    )
    ranked_frame = payload["ranked_pool"]
    order_fields = (
        "final_rank_score_v2",
        "activation_rank_percentile",
        "repair_rank_percentile",
    )
    missing_order_fields = [
        field for field in order_fields if field not in ranked_frame.columns
    ]
    if missing_order_fields:
        raise ValueError(
            "ranked_pool missing required columns: "
            + ", ".join(missing_order_fields)
        )
    order_values = ranked_frame.loc[:, order_fields].apply(
        pd.to_numeric, errors="coerce"
    )
    if order_values.isna().any().any() or not np.isfinite(order_values).all().all():
        raise ValueError("ranked_pool V2 score ordering fields must be finite")
    expected_ranked_ids = ranked_frame.sort_values(
        [*order_fields, "asset_id"],
        ascending=[False, False, False, True],
        kind="stable",
    )["asset_id"].astype(str).str.strip().tolist()
    if ranked_ids != expected_ranked_ids:
        raise ValueError("ranked_pool order must follow V2 score ordering")
    top20_ids = _validate_v2_rank_frame(payload["top20"], "top20", start_rank=1)
    top30_ids = _validate_v2_rank_frame(payload["top30"], "top30", start_rank=1)
    final_top_n = int(coverage.get("final_top_n", 20))
    reserve_top_n = int(coverage.get("reserve_top_n", 20))
    reserve_ids = _validate_v2_rank_frame(
        payload["reserve"],
        "reserve",
        start_rank=final_top_n + 1,
    )
    pool_size = len(ranked_ids)
    expected_top20_count = min(final_top_n, pool_size)
    expected_top30_count = min(30, pool_size)
    expected_reserve_count = min(
        reserve_top_n,
        max(0, pool_size - final_top_n),
    )
    for name, actual_count, expected_count in (
        ("top20", len(top20_ids), expected_top20_count),
        ("top30", len(top30_ids), expected_top30_count),
        ("reserve", len(reserve_ids), expected_reserve_count),
    ):
        if actual_count != expected_count:
            raise ValueError(
                f"{name} length must equal ranked_pool selection size"
            )
    if len(top20_ids) > final_top_n:
        raise ValueError("top20 length must not exceed final_top_n")
    if len(top30_ids) > 30:
        raise ValueError("top30 length must not exceed 30")
    if len(reserve_ids) > reserve_top_n:
        raise ValueError("reserve length must not exceed reserve_top_n")
    if top20_ids != ranked_ids[: len(top20_ids)]:
        raise ValueError("top20 must equal the ranked_pool prefix")
    if top30_ids != ranked_ids[: len(top30_ids)]:
        raise ValueError("top30 must equal the ranked_pool prefix")
    expected_reserve = ranked_ids[final_top_n : final_top_n + len(reserve_ids)]
    if reserve_ids != expected_reserve:
        raise ValueError("reserve must follow top20 in ranked_pool order")
    _validate_v2_selection_values(
        payload["top20"],
        ranked_frame.iloc[:expected_top20_count],
        "top20",
    )
    _validate_v2_selection_values(
        payload["top30"],
        ranked_frame.iloc[:expected_top30_count],
        "top30",
    )
    _validate_v2_selection_values(
        payload["reserve"],
        ranked_frame.iloc[
            final_top_n : final_top_n + expected_reserve_count
        ],
        "reserve",
    )
    if set(top20_ids) & set(reserve_ids):
        raise ValueError("top20 and reserve must be disjoint")
    preaudit_ids = set(payload["preaudit"]["asset_id"].astype(str).str.strip())
    if not (set(top20_ids) | set(reserve_ids)).issubset(preaudit_ids):
        raise ValueError("selected assets must be present in preaudit")

    status = coverage.get("publication_status")
    if status not in {"ready", "coverage_insufficient", "preaudit_only"}:
        raise ValueError("coverage publication_status is invalid")
    if status == "preaudit_only":
        if ranked_ids or top20_ids or top30_ids or reserve_ids:
            raise ValueError("preaudit_only publication must not include ranked selections")
    else:
        expected_status = "ready" if len(ranked_ids) >= 30 else "coverage_insufficient"
        if status != expected_status:
            raise ValueError(
                f"coverage publication_status must be {expected_status} for ranked pool size"
            )
    if int(coverage.get("v2_ranked_pool_count", -1)) != len(ranked_ids):
        raise ValueError("v2_ranked_pool_count must equal ranked_pool length")
    if int(coverage.get("v2_top30_count", -1)) != len(top30_ids):
        raise ValueError("v2_top30_count must equal top30 length")
    activation_funnel = coverage.get("activation_funnel", {})
    for key, expected_count in (
        ("ranked_pool", len(ranked_ids)),
        ("top20", len(top20_ids)),
        ("top30", len(top30_ids)),
        ("reserve", len(reserve_ids)),
    ):
        if int(activation_funnel.get(key, -1)) != expected_count:
            raise ValueError(f"activation_funnel {key} must equal frame length")
    unified_funnel = coverage.get("unified_funnel", {})
    for key, expected_count in (
        ("preaudit", len(payload["preaudit"])),
        ("final", len(top20_ids)),
        ("reserve", len(reserve_ids)),
    ):
        if int(unified_funnel.get(key, -1)) != expected_count:
            raise ValueError(f"unified_funnel {key} must equal frame length")


def _publish_v2_compatible_artifacts(
    payload: dict[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Publish current V2 core frames without applying V1 fixed-size validation."""
    _validate_v2_compatibility_payload(payload)
    frames: dict[str, pd.DataFrame] = {}
    for key in V2_COMPATIBILITY_PUBLICATION_FRAME_KEYS:
        frame = payload[key]
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{key} must be a pandas DataFrame")
        frames[key] = (
            _ordered_evidence_frame(frame)
            if key == "evidence"
            else _ordered_frame(frame)
        )
    coverage = _json_safe(copy.deepcopy(payload["coverage"]))
    coverage["trade_date"] = payload["trade_date"]
    report = _render_report(
        payload["trade_date"],
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
        _publish_release(destination, frames, coverage, report)
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
    paths = {
        key: str(destination / "current" / filename)
        for key, filename in UNIFIED_OUTPUT_FILENAMES.items()
    }
    return {
        "paths": paths,
        **frames,
        "coverage": coverage,
        "report": report,
    }


def _add_publication_thresholds(
    coverage: dict[str, Any], config: ConsumerOversoldConfig
) -> None:
    coverage.update(
        final_top_n=config.final_top_n,
        reserve_top_n=config.reserve_top_n,
        preaudit_size=config.preaudit_size,
        minimum_evidence_complete=config.minimum_evidence_complete,
    )
    threshold_warning = (
        "publication_thresholds: "
        f"final_top_n={config.final_top_n}, reserve_top_n={config.reserve_top_n}, "
        f"preaudit_size={config.preaudit_size}, "
        f"minimum_evidence_complete={config.minimum_evidence_complete}"
    )
    coverage["warnings"] = sorted(set([*coverage.get("warnings", []), threshold_warning]))


def _copy_frames(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    if not isinstance(frames, dict):
        raise TypeError("frames must be a dict")
    missing = [key for key in REQUIRED_FRAME_KEYS if key not in frames]
    if missing:
        raise ValueError(f"missing required frame keys: {', '.join(missing)}")
    copied: dict[str, pd.DataFrame] = {}
    for key, frame in frames.items():
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"frames[{key!r}] must be a pandas DataFrame")
        copied[key] = frame.copy(deep=True)
    return copied


def _require_downstream_columns(frames: dict[str, pd.DataFrame]) -> None:
    requirements = (
        ("bars", BAR_COLUMNS),
        ("share_capacity", MARKET_CAPACITY_SHARE_COLUMNS),
        ("finance", FEATURE_FINANCE_COLUMNS),
        ("current_valuation", CURRENT_VALUATION_COLUMNS),
        ("valuation_history", VALUATION_HISTORY_COLUMNS),
    )
    for frame_name, required in requirements:
        missing = [column for column in required if column not in frames[frame_name].columns]
        if missing:
            raise ValueError(f"{frame_name} missing required columns: {', '.join(missing)}")


def _normalize_asset_ids(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if "asset_id" not in result.columns:
        raise ValueError(f"{name} missing required columns: asset_id")
    if result.empty:
        return result
    missing = result["asset_id"].isna()
    result["asset_id"] = result["asset_id"].astype(str).str.strip()
    if (missing | result["asset_id"].eq("")).any():
        raise ValueError(f"{name} asset_id must be non-empty")
    duplicate = result["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = result.loc[duplicate, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"{name} contains duplicate asset_id {asset_id}")
    return result


def _merge_one_to_one(left: pd.DataFrame, right: pd.DataFrame, name: str) -> pd.DataFrame:
    normalized = _normalize_asset_ids(right, name)
    return left.merge(normalized, on="asset_id", how="left", validate="one_to_one")


def _drop_invalid_technical_histories(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Remove whole asset histories that cannot satisfy the strict technical API."""
    required = ("asset_id", "trade_date", "close", "amount", "turnover_rate")
    if bars.empty or any(column not in bars.columns for column in required):
        return bars.copy(deep=True)

    frame = bars.copy(deep=True)
    parsed_dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    historical = frame.loc[parsed_dates.le(pd.Timestamp(trade_date))]
    invalid = pd.Series(False, index=historical.index, dtype=bool)
    numeric_types = (int, float, np.integer, np.floating, Decimal)
    for field in ("close", "amount", "turnover_rate"):
        def valid(value: object) -> bool:
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, numeric_types
            ):
                return False
            try:
                number = float(value)
            except (OverflowError, TypeError, ValueError):
                return False
            if not math.isfinite(number):
                return False
            return number > 0.0 if field == "close" else number >= 0.0

        invalid |= ~historical[field].map(valid)
    invalid_asset_ids = set(
        historical.loc[invalid, "asset_id"].astype(str)
    )
    if not invalid_asset_ids:
        return frame
    return frame.loc[
        ~frame["asset_id"].astype(str).isin(invalid_asset_ids)
    ].copy()


def _empty_evidence_defaults(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    text_defaults = {
        "stock_code_evidence": "",
        "evidence_as_of_date": "",
        "repair_bucket": "",
        "repair_thesis": "",
        "leading_indicator": "",
        "unrepaired_metrics": "",
        "expected_validation_date": "",
        "main_risks": "",
        "invalidation_conditions": "",
        "source_title": "",
        "source_url": "",
        "source_publish_date": "",
        "forecast_revision_state": "unknown",
        "audit_review_status": "unknown",
        "pledge_debt_review_status": "unknown",
        "permanent_impairment_status": "unknown",
        "operator_notes": "",
        "evidence_errors": "missing_evidence",
    }
    for column, default in text_defaults.items():
        if column not in result.columns:
            result[column] = default
        else:
            result[column] = result[column].where(result[column].notna(), default)
    for column in ("catalyst_verifiability_score", "expected_improvement_score"):
        if column not in result.columns:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if "evidence_complete" not in result.columns:
        result["evidence_complete"] = False
    result["evidence_complete"] = result["evidence_complete"].fillna(False).astype(bool)
    if "hard_risk_manual_trigger" not in result.columns:
        result["hard_risk_manual_trigger"] = False
    result["hard_risk_manual_trigger"] = result["hard_risk_manual_trigger"].fillna(False).astype(bool)
    if "repair_already_completed" in result.columns:
        result["repair_already_completed"] = result["repair_already_completed"].fillna(False)
    for column in (
        "audit_review_status",
        "pledge_debt_review_status",
        "permanent_impairment_status",
    ):
        result[column] = result[column].replace("", "unknown").fillna("unknown")
    return result


def _maximum_date(frame: pd.DataFrame, field: str, cutoff: str) -> str | None:
    if field not in frame.columns or frame.empty:
        return None
    parsed = pd.to_datetime(frame[field], errors="coerce")
    parsed = parsed.loc[parsed.le(pd.Timestamp(cutoff))]
    if parsed.empty or parsed.isna().all():
        return None
    return parsed.max().date().isoformat()


def _count_missing(frame: pd.DataFrame, fields: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in fields:
        counts[field] = int(frame[field].isna().sum()) if field in frame.columns else len(frame)
    return counts


def _coverage(
    *,
    raw_assets: pd.DataFrame,
    included: pd.DataFrame,
    scores: pd.DataFrame,
    evidence: pd.DataFrame,
    bars: pd.DataFrame,
    finance: pd.DataFrame,
    valuation_history: pd.DataFrame,
    expected: pd.DataFrame,
    early: pd.DataFrame,
    config: ConsumerOversoldConfig,
    warnings: list[str],
) -> dict[str, Any]:
    price_pass = (
        scores["price_history_complete"].fillna(False).astype(bool)
        & (
            scores["return_6m"].le(config.min_6m_return)
            | scores["max_drawdown_12m"].le(config.min_12m_drawdown)
        )
        & scores["relative_return_coverage"].fillna(False).astype(bool)
    )
    repair_threshold = (
        scores["composite_score"].ge(config.v2_min_composite_score)
        if config.ranking_version == "v2" and "composite_score" in scores
        else scores["oversold_score"].ge(config.min_oversold_score)
    )
    oversold_pass = (
        price_pass
        & scores["relative_return_6m"].le(config.min_relative_return)
        & repair_threshold
    )
    risk_pass = (
        oversold_pass
        & ~scores["hard_risk_triggered"].fillna(False).astype(bool)
        & ~scores["hard_risk_review_unknown"].fillna(True).astype(bool)
    )
    evidence_pass = risk_pass & scores["evidence_complete"].fillna(False).astype(bool)
    valuation_pass = evidence_pass & scores["base_upside"].ge(config.min_base_upside)
    included_ids = set(included["asset_id"].astype(str))
    valuation_ids = set(valuation_history.get("asset_id", pd.Series(dtype=object)).astype(str))
    finance_ids = set(finance.get("asset_id", pd.Series(dtype=object)).astype(str))
    total = len(included_ids)
    return {
        "funnel": {
            "raw_assets": int(raw_assets["asset_id"].astype(str).nunique()) if "asset_id" in raw_assets else 0,
            "consumer_universe": int(len(included)),
            "market_eligible": int(price_pass.sum()),
            "oversold_eligible": int(oversold_pass.sum()),
            "hard_risk_clear": int(risk_pass.sum()),
            "evidence_complete": int(evidence_pass.sum()),
            "valuation_eligible": int(valuation_pass.sum()),
            "selected_expected": int(len(expected)),
            "selected_early": int(len(early)),
        },
        "data_date_maxima": {
            "market": _maximum_date(bars, "trade_date", config.trade_date),
            "finance": _maximum_date(finance, "announcement_date", config.trade_date),
            "evidence": _maximum_date(evidence, "evidence_as_of_date", config.trade_date),
            "valuation": _maximum_date(valuation_history, "valuation_date", config.trade_date),
        },
        "missing_field_counts": _count_missing(
            scores,
            (
                "return_6m",
                "relative_return_6m",
                "oversold_score",
                "latest_announcement_date",
                "base_upside",
                "valuation_depression_percentile",
                "repair_thesis",
            ),
        ),
        "warnings": sorted(set(warnings)),
        "valuation_history_coverage": {
            "covered": int(len(included_ids & valuation_ids)),
            "total": int(total),
        },
        "finance_history_coverage": {
            "covered": int(len(included_ids & finance_ids)),
            "total": int(total),
        },
    }


def _prepare_valuation_inputs(
    current_valuation: pd.DataFrame,
    valuation_history: pd.DataFrame,
    fundamentals: pd.DataFrame,
    membership: pd.DataFrame,
    trade_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    current = current_valuation.copy(deep=True)
    history = valuation_history.copy(deep=True)
    for frame, required, name in (
        (current, CURRENT_VALUATION_COLUMNS, "current_valuation"),
        (history, VALUATION_HISTORY_COLUMNS, "valuation_history"),
    ):
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{name} missing required columns: {', '.join(missing)}")
    current = _normalize_asset_ids(current, "current_valuation")
    membership_map = membership.set_index("asset_id")["consumer_subindustry"]
    current = current.loc[current["asset_id"].isin(membership_map.index)].copy()
    current["consumer_subindustry"] = current["asset_id"].map(membership_map)
    current["as_of_date"] = trade_date
    history["asset_id"] = history["asset_id"].astype(str)
    history = history.loc[history["asset_id"].isin(membership_map.index)].copy()
    history["consumer_subindustry"] = history["asset_id"].map(membership_map)
    warnings: list[str] = []
    if current["net_debt"].isna().any() or current["ebitda_ttm"].isna().any():
        warnings.append("net_debt_or_ebitda_ttm_unavailable; EV/EBITDA valuation is not assumed to be zero")
    market_cap = pd.to_numeric(current["current_market_cap"], errors="coerce")
    invalid_cap = market_cap.isna() | ~np.isfinite(market_cap) | market_cap.le(0.0)
    if invalid_cap.any():
        warnings.append(f"current_market_cap_unavailable_for_{int(invalid_cap.sum())}_assets")
    fundamental_ids = set(fundamentals.get("asset_id", pd.Series(dtype=object)).astype(str))
    valid = current.loc[~invalid_cap & current["asset_id"].isin(fundamental_ids)].copy()
    needed_fundamentals = fundamentals.loc[fundamentals["asset_id"].isin(valid["asset_id"])].copy()
    return valid, history, needed_fundamentals, warnings


def _apply_automatic_gates(
    rows: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    result = rows.copy()
    if config.ranking_version == "v2":
        result["v2_quantitative_repair_score"] = (
            0.35 * result["oversold_score"]
            + 0.30 * result["valuation_repair_score"]
            + 0.20 * result["operating_gap_score"]
            + 0.15 * result["balance_sheet_score"]
        )
    price_pass = result["return_6m"].le(config.min_6m_return) | result[
        "max_drawdown_12m"
    ].le(config.min_12m_drawdown)
    repair_completed = result.get(
        "repair_already_completed", pd.Series(False, index=result.index)
    ).fillna(False).astype(bool) | result["exclusion_reasons"].fillna("").str.contains(
        "repair_already_completed", regex=False
    )
    required_numeric = (
        "relative_return_6m",
        "oversold_score",
        "base_upside",
        "valuation_percentile",
        "valuation_repair_score",
        "operating_gap_score",
        "balance_sheet_score",
        "drawdown_from_high_1y",
        "drawdown_from_high_2y",
        "price_position_1y",
        "price_position_2y",
        "distance_hfq_ma120",
        "distance_hfq_ma250",
        "rebound_from_low_60d",
        "rebound_from_low_120d",
        "limit_up_count_2y",
        "up_7pct_count_2y",
        "up_5pct_count_2y",
        "upside_tail_volatility_2y",
        "positive_after_big_up_1d_rate",
        "positive_after_big_up_3d_rate",
        "positive_after_big_up_5d_rate",
        "log_current_float_market_cap",
    )
    quantitative_values = result.loc[:, required_numeric].copy()
    no_big_up = (
        result["stock_character_coverage"].fillna(False).astype(bool)
        & result["up_7pct_count_2y"].eq(0.0)
    )
    for field in (
        "positive_after_big_up_1d_rate",
        "positive_after_big_up_3d_rate",
        "positive_after_big_up_5d_rate",
    ):
        quantitative_values.loc[
            no_big_up & quantitative_values[field].isna(), field
        ] = 0.0
    quantitative_complete = quantitative_values.notna().all(axis=1)
    masks = {
        "universe_excluded": result["included"].fillna(False).astype(bool),
        "price_threshold_not_met": price_pass,
        "relative_return_threshold_not_met": result["relative_return_6m"].le(
            config.min_relative_return
        ),
        "base_upside_below_threshold": result["base_upside"].ge(
            config.min_base_upside
        ),
        "balance_sheet_coverage_insufficient": result[
            "balance_sheet_coverage"
        ].fillna(False).astype(bool),
        "automatic_hard_risk_triggered": ~result[
            "automatic_hard_risk_triggered"
        ].fillna(False).astype(bool),
        "automatic_risk_review_unknown": ~result[
            "automated_risk_review_unknown"
        ].fillna(True).astype(bool),
        "repair_already_completed": ~repair_completed,
        "quantitative_fields_incomplete": quantitative_complete,
        "price_history_coverage_incomplete": result[
            "price_history_complete"
        ].fillna(False).astype(bool),
        "relative_return_coverage_incomplete": result[
            "relative_return_coverage"
        ].fillna(False).astype(bool),
        "residual_deviation_coverage_incomplete": result[
            "residual_deviation_coverage"
        ].fillna(False).astype(bool),
        "stock_character_coverage_incomplete": result[
            "stock_character_coverage"
        ].fillna(False).astype(bool),
        "market_capacity_coverage_incomplete": result[
            "market_capacity_coverage"
        ].fillna(False).astype(bool),
    }
    if config.ranking_version == "v1":
        masks["oversold_score_below_threshold"] = result["oversold_score"].ge(
            config.min_oversold_score
        )
    else:
        masks["quantitative_repair_score_below_v2_threshold"] = result[
            "v2_quantitative_repair_score"
        ].ge(config.v2_min_composite_score)
    eligible = pd.Series(True, index=result.index, dtype=bool)
    for mask in masks.values():
        eligible &= mask
    result["automatic_eligible"] = eligible.astype(bool)
    result["automatic_exclusion_reasons"] = [
        "|".join(sorted(reason for reason, mask in masks.items() if not bool(mask.loc[index])))
        for index in result.index
    ]
    return result


def _build_rank_comparison(
    scored: pd.DataFrame,
    legacy: dict[str, pd.DataFrame],
    unified: pd.DataFrame,
) -> pd.DataFrame:
    comparison = scored.copy()
    old_pool = comparison.loc[comparison["eligible"].astype(bool)].sort_values(
        ["composite_score", "asset_id"],
        ascending=[False, True],
        kind="stable",
    )
    old_combined = pd.Series(
        np.arange(1, len(old_pool) + 1, dtype=int), index=old_pool["asset_id"]
    )
    bucket_rows = pd.concat(
        [
            frame.loc[:, ["asset_id", "bucket_rank"]]
            for frame in (legacy["expected"], legacy["early"])
            if not frame.empty
        ],
        ignore_index=True,
    ) if any(not frame.empty for frame in legacy.values()) else pd.DataFrame(
        columns=["asset_id", "bucket_rank"]
    )
    bucket_rank = bucket_rows.set_index("asset_id")["bucket_rank"]
    if unified.empty:
        new_rank = pd.Series(dtype=float)
        new_final_rank_score = pd.Series(dtype=float)
    else:
        unified_by_asset = unified.set_index("asset_id")
        new_rank = unified_by_asset["final_rank"]
        new_final_rank_score = unified_by_asset["final_rank_score"]
    comparison["old_bucket_rank"] = comparison["asset_id"].map(bucket_rank)
    comparison["old_combined_rank"] = comparison["asset_id"].map(old_combined)
    comparison["new_rank"] = comparison["asset_id"].map(new_rank)
    comparison["final_rank_score"] = comparison["asset_id"].map(
        new_final_rank_score
    )
    comparison["rank_change"] = (
        comparison["old_combined_rank"] - comparison["new_rank"]
    )
    return comparison.reindex(columns=COMPARISON_COLUMNS).sort_values(
        "asset_id", kind="stable"
    ).reset_index(drop=True)


def _build_v1_reference(
    scored: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> dict[str, Any]:
    v1_config = replace(config, ranking_version="v1")
    gated = apply_candidate_gates(scored, v1_config)
    automatically_gated = _apply_automatic_gates(gated, v1_config)
    elasticity_scored = score_rebound_elasticity(automatically_gated, v1_config)
    ranked = rank_candidate_buckets(elasticity_scored, v1_config)
    elasticity_scored["preaudit_score"] = (
        0.30 * elasticity_scored["oversold_score"]
        + 0.25 * elasticity_scored["valuation_repair_score"]
        + 0.20 * elasticity_scored["operating_gap_score"]
        + 0.15 * elasticity_scored["balance_sheet_score"]
        + 0.10 * elasticity_scored["automatic_elasticity_score"]
    ).where(
        elasticity_scored["automatic_eligible"]
        & elasticity_scored["automatic_elasticity_coverage"]
    )
    preaudit_full = elasticity_scored.loc[
        elasticity_scored["preaudit_score"].notna()
    ].sort_values(
        ["preaudit_score", "oversold_score", "asset_id"],
        ascending=[False, False, True],
        kind="stable",
    ).head(v1_config.preaudit_size).reset_index(drop=True)
    preaudit_ids = set(preaudit_full["asset_id"].astype(str))
    final_scored = score_rebound_elasticity(
        automatically_gated.loc[
            automatically_gated["asset_id"].isin(preaudit_ids)
        ].copy(),
        v1_config,
    )
    unified = rank_unified_candidates(final_scored, v1_config)
    final_score_columns = (
        "residual_deviation_component_coverage",
        "residual_deviation_score",
        "stock_character_component_coverage",
        "stock_character_score",
        "market_capacity_component_coverage",
        "market_capacity_score",
        "catalyst_liquidity_coverage",
        "catalyst_liquidity_score",
        "elasticity_coverage",
        "elasticity_score",
    )
    final_scores_by_asset = final_scored.set_index("asset_id")
    for field in final_score_columns:
        elasticity_scored[field] = elasticity_scored["asset_id"].map(
            final_scores_by_asset[field]
        )
    return {
        "config": v1_config,
        "scored": elasticity_scored,
        "ranked": ranked,
        "preaudit_full": preaudit_full,
        "preaudit": preaudit_full.reindex(columns=PREAUDIT_OUTPUT_COLUMNS),
        "preaudit_ids": preaudit_ids,
        "final_scored": final_scored,
        "unified": unified,
    }


def _build_v2_preaudit(
    activation_scored: pd.DataFrame,
    v1_reference: dict[str, Any],
    v2_ranked: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> tuple[pd.DataFrame, set[str]]:
    candidates = activation_scored.copy()
    candidates["v2_quantitative_preaudit_score"] = (
        0.30 * candidates["oversold_score"]
        + 0.25 * candidates["valuation_repair_score"]
        + 0.20 * candidates["operating_gap_score"]
        + 0.15 * candidates["balance_sheet_score"]
        + 0.10 * candidates["automatic_elasticity_score"]
    ).where(
        candidates["automatic_eligible"]
        & candidates["automatic_elasticity_coverage"]
    )
    candidates["preaudit_score"] = (
        config.v2_repair_rank_weight * candidates["composite_score"]
        + config.v2_activation_rank_weight * candidates["activation_score"]
    ).where(candidates["eligible"] & candidates["activation_coverage"])
    candidates.loc[
        candidates["eligible"] & candidates["preaudit_score"].isna(),
        "preaudit_score",
    ] = candidates["composite_score"]
    quantitative_candidates = (
        candidates["automatic_eligible"]
        & candidates["automatic_elasticity_coverage"]
    )
    candidates.loc[
        quantitative_candidates & candidates["preaudit_score"].isna(),
        "preaudit_score",
    ] = candidates["v2_quantitative_preaudit_score"]
    quantitative_priority = candidates.loc[quantitative_candidates].sort_values(
        [
            "evidence_complete",
            "preaudit_score",
            "v2_quantitative_repair_score",
            "oversold_score",
            "asset_id",
        ],
        ascending=[True, False, False, False, True],
        kind="stable",
        na_position="last",
    )
    formal_selection_size = min(
        config.preaudit_size,
        config.final_top_n + config.reserve_top_n,
    )
    selected_ids = (
        v2_ranked["asset_id"].astype(str).head(formal_selection_size).tolist()
    )
    selected_set = set(selected_ids)
    if len(selected_ids) < config.preaudit_size:
        for asset_id in quantitative_priority["asset_id"].astype(str):
            if asset_id in selected_set:
                continue
            selected_ids.append(asset_id)
            selected_set.add(asset_id)
            if len(selected_ids) >= config.preaudit_size:
                break
    if len(selected_ids) < config.preaudit_size:
        for asset_id in v2_ranked["asset_id"].astype(str):
            if asset_id in selected_set:
                continue
            selected_ids.append(asset_id)
            selected_set.add(asset_id)
            if len(selected_ids) >= config.preaudit_size:
                break
    if len(selected_ids) < config.preaudit_size:
        for asset_id in v1_reference["preaudit_full"]["asset_id"].astype(str):
            if asset_id in selected_set:
                continue
            selected_ids.append(asset_id)
            selected_set.add(asset_id)
            if len(selected_ids) >= config.preaudit_size:
                break

    by_asset = candidates.set_index("asset_id", drop=False)
    preaudit_full = (
        by_asset.loc[selected_ids].copy()
        if selected_ids
        else candidates.iloc[0:0].copy()
    )
    v1_preaudit_score = v1_reference["preaudit_full"].set_index("asset_id")[
        "preaudit_score"
    ]
    missing_score = preaudit_full["preaudit_score"].isna()
    preaudit_full.loc[missing_score, "preaudit_score"] = preaudit_full.loc[
        missing_score, "asset_id"
    ].map(v1_preaudit_score)
    preaudit_full = preaudit_full.reset_index(drop=True)
    return preaudit_full.reindex(columns=V2_PREAUDIT_OUTPUT_COLUMNS), selected_set


def _build_v2_comparison(
    activation_scored: pd.DataFrame,
    v1_reference: dict[str, Any],
    v2_ranked: pd.DataFrame,
) -> pd.DataFrame:
    comparison = activation_scored.loc[
        :, ["asset_id", "stock_code", "stock_name", "composite_score", "activation_score"]
    ].copy()
    v1_scored = v1_reference["scored"].set_index("asset_id")
    v1_ranked = v1_reference["unified"].set_index("asset_id")
    v2_by_asset = v2_ranked.set_index("asset_id")
    comparison["v1_rank"] = comparison["asset_id"].map(v1_ranked["final_rank"])
    comparison["v2_rank"] = comparison["asset_id"].map(v2_by_asset["final_rank"])
    comparison["rank_change"] = comparison["v1_rank"] - comparison["v2_rank"]
    comparison["v1_final_rank_score"] = comparison["asset_id"].map(
        v1_ranked["final_rank_score"]
    )
    comparison["v1_repair_score"] = comparison["asset_id"].map(
        v1_scored["composite_score"]
    )
    comparison["v1_elasticity_score"] = comparison["asset_id"].map(
        v1_scored["elasticity_score"]
    )
    comparison["v2_repair_score"] = comparison["composite_score"]
    comparison["v2_activation_score"] = comparison["activation_score"]
    comparison["v2_final_rank_score"] = comparison["asset_id"].map(
        v2_by_asset["final_rank_score_v2"]
    )
    comparison["v1_exclusion_reasons"] = comparison["asset_id"].map(
        v1_scored["exclusion_reasons"]
    )
    gate_reasons = activation_scored.set_index("asset_id")["exclusion_reasons"]
    activation_reasons = activation_scored.set_index("asset_id")[
        "activation_exclusion_reasons"
    ]
    comparison["v2_exclusion_reasons"] = [
        str(gate_reasons.get(asset_id, "") or "")
        or str(activation_reasons.get(asset_id, "") or "")
        for asset_id in comparison["asset_id"]
    ]
    return comparison.reindex(columns=V2_COMPARISON_COLUMNS).sort_values(
        "asset_id", kind="stable"
    ).reset_index(drop=True)


def _build_v2_result(
    *,
    copied: dict[str, pd.DataFrame],
    universe: pd.DataFrame,
    included: pd.DataFrame,
    membership: pd.DataFrame,
    bars: pd.DataFrame,
    finance: pd.DataFrame,
    valuation_history: pd.DataFrame,
    validated_evidence: pd.DataFrame,
    scored: pd.DataFrame,
    config: ConsumerOversoldConfig,
    warnings: list[str],
    output_dir: str | Path | None,
    preaudit_only: bool,
) -> dict[str, Any]:
    gated = apply_candidate_gates(scored, config)
    automatically_gated = _apply_automatic_gates(gated, config)
    elasticity_scored = score_rebound_elasticity(automatically_gated, config)
    technical_bars = _drop_invalid_technical_histories(
        bars,
        trade_date=config.trade_date,
    )
    technical = compute_technical_readiness_features(
        technical_bars,
        membership,
        trade_date=config.trade_date,
    ).drop(columns=["latest_trade_date"], errors="ignore")
    activation_input = _merge_one_to_one(
        elasticity_scored,
        technical,
        "technical_readiness_features",
    )
    activation_scored = score_activation_candidates(activation_input, config)
    activation_scored["ranking_version"] = "v2"

    v1_reference = _build_v1_reference(scored, config)
    ranked_pool_full = rank_v2_candidates(activation_scored, config)
    ranked_pool = (
        ranked_pool_full.iloc[0:0].copy() if preaudit_only else ranked_pool_full.copy()
    )
    preaudit, preaudit_ids = _build_v2_preaudit(
        activation_scored,
        v1_reference,
        ranked_pool_full,
        config,
    )

    top20 = ranked_pool.loc[
        ranked_pool["final_rank"].le(config.final_top_n)
    ].copy()
    top30 = ranked_pool.loc[ranked_pool["final_rank"].le(30)].copy()
    reserve_limit = config.final_top_n + config.reserve_top_n
    reserve = ranked_pool.loc[
        ranked_pool["final_rank"].gt(config.final_top_n)
        & ranked_pool["final_rank"].le(reserve_limit)
    ].copy()
    for frame in (ranked_pool, top20, top30, reserve):
        frame["trade_date"] = config.trade_date
    ranked_pool = ranked_pool.reindex(columns=V2_OUTPUT_COLUMNS)
    top20 = top20.reindex(columns=V2_OUTPUT_COLUMNS)
    top30 = top30.reindex(columns=V2_OUTPUT_COLUMNS)
    reserve = reserve.reindex(columns=V2_OUTPUT_COLUMNS)
    comparison = _build_v2_comparison(
        activation_scored,
        v1_reference,
        ranked_pool,
    )

    universe_exclusions = universe.loc[~universe["included"].astype(bool)].rename(
        columns={
            "name": "stock_name",
            "exclude_reasons": "exclusion_reasons",
        }
    )
    universe_exclusions["exclusion_stage"] = "universe"
    universe_exclusions = universe_exclusions.reindex(columns=EXCLUSION_ID_COLUMNS)
    candidate_exclusions = activation_scored.loc[
        ~activation_scored["eligible"] | ~activation_scored["activation_eligible"]
    ].copy()
    activation_failed = candidate_exclusions["eligible"].astype(bool)
    candidate_exclusions["exclusion_stage"] = np.where(
        activation_failed,
        "activation",
        "gate",
    )
    candidate_exclusions.loc[activation_failed, "exclusion_reasons"] = (
        candidate_exclusions.loc[activation_failed, "activation_exclusion_reasons"]
    )
    exclusion_columns = [
        *EXCLUSION_ID_COLUMNS,
        *[
            column
            for column in candidate_exclusions.columns
            if column not in EXCLUSION_ID_COLUMNS
        ],
    ]
    candidate_exclusions = candidate_exclusions.reindex(columns=exclusion_columns)
    exclusions = pd.concat(
        [universe_exclusions, candidate_exclusions],
        ignore_index=True,
        sort=False,
    ).sort_values(["exclusion_stage", "asset_id"], kind="stable").reset_index(
        drop=True
    )

    ranked_count = len(ranked_pool)
    publication_warnings: list[str] = []
    if not preaudit_only and ranked_count < 30:
        publication_warnings.append("v2_ranked_pool_below_30")
    publication_status = (
        "preaudit_only"
        if preaudit_only
        else "ready" if not publication_warnings else "coverage_insufficient"
    )
    reviewed_evidence_ids = set(validated_evidence["asset_id"].astype(str))
    complete_evidence_ids = set(
        validated_evidence.loc[
            validated_evidence["evidence_complete"].fillna(False).astype(bool),
            "asset_id",
        ].astype(str)
    )
    v1_automatic_ids = set(
        v1_reference["scored"].loc[
            v1_reference["scored"]["automatic_eligible"].astype(bool),
            "asset_id",
        ].astype(str)
    )
    v2_automatic_ids = set(
        activation_scored.loc[
            activation_scored["automatic_eligible"].astype(bool),
            "asset_id",
        ].astype(str)
    )
    v2_first_gate_ids = set(
        activation_scored.loc[
            activation_scored["eligible"].astype(bool),
            "asset_id",
        ].astype(str)
    )
    automatic_ids = v1_automatic_ids | v2_automatic_ids | v2_first_gate_ids
    activation_complete_ids = set(
        activation_scored.loc[
            activation_scored["activation_coverage"].astype(bool),
            "asset_id",
        ].astype(str)
    )
    preaudit_evidence_reviewed = len(preaudit_ids & reviewed_evidence_ids)
    preaudit_evidence_complete = len(preaudit_ids & complete_evidence_ids)
    preaudit_activation_complete = len(
        preaudit_ids & complete_evidence_ids & activation_complete_ids
    )

    coverage = _coverage(
        raw_assets=copied["assets"],
        included=included,
        scores=activation_scored,
        evidence=validated_evidence,
        bars=bars,
        finance=finance,
        valuation_history=valuation_history,
        expected=v1_reference["ranked"]["expected"],
        early=v1_reference["ranked"]["early"],
        config=config,
        warnings=[*warnings, *publication_warnings],
    )
    unified_funnel = {
        "full": int(len(activation_scored)),
        "automatic": int(len(automatic_ids)),
        "preaudit": int(len(preaudit)),
        "evidence_reviewed": int(preaudit_evidence_reviewed),
        "evidence_complete": int(preaudit_evidence_complete),
        "elasticity_complete": int(preaudit_activation_complete),
        "final": int(len(top20)),
        "reserve": int(len(reserve)),
    }
    coverage["unified_funnel"] = unified_funnel
    coverage["funnel"].update(
        {
            key: value
            for key, value in unified_funnel.items()
            if key != "evidence_complete"
        }
    )
    coverage.update(
        ranking_version="v2",
        publication_status=publication_status,
        full_pool_evidence_complete=int(
            activation_scored["evidence_complete"].fillna(False).astype(bool).sum()
        ),
        v2_ranked_pool_count=int(ranked_count),
        v2_top30_count=int(len(top30)),
        v2_thresholds={
            "min_6m_return": config.min_6m_return,
            "min_12m_drawdown": config.min_12m_drawdown,
            "min_relative_return": config.min_relative_return,
            "min_base_upside": config.min_base_upside,
            "min_composite_score": config.v2_min_composite_score,
            "min_technical_readiness_score": config.v2_min_technical_readiness_score,
        },
        v2_rank_weights={
            "repair": config.v2_repair_rank_weight,
            "activation": config.v2_activation_rank_weight,
        },
        v2_activation_weights={
            "technical_readiness": config.technical_readiness_weight,
            "continuation_character": config.continuation_character_weight,
            "residual_price_space": config.residual_price_space_weight,
            "capital_efficiency": config.capital_efficiency_weight,
            "catalyst_timing": config.catalyst_timing_weight,
        },
        activation_funnel={
            "first_gate_eligible": int(activation_scored["eligible"].sum()),
            "activation_covered": int(activation_scored["activation_coverage"].sum()),
            "activation_eligible": int(activation_scored["activation_eligible"].sum()),
            "ranked_pool": int(ranked_count),
            "top20": int(len(top20)),
            "top30": int(len(top30)),
            "reserve": int(len(reserve)),
        },
    )
    coverage["warnings"] = sorted(
        set([*coverage["warnings"], *publication_warnings])
    )
    _add_publication_thresholds(coverage, config)
    payload = {
        "trade_date": config.trade_date,
        "evidence": validated_evidence,
        "scores": activation_scored,
        "exclusions": exclusions,
        "coverage": coverage,
        "top20": top20,
        "reserve": reserve,
        "preaudit": preaudit,
        "comparison": comparison,
        "top30": top30,
        "ranked_pool": ranked_pool,
    }
    if output_dir is not None:
        published = write_consumer_oversold_artifacts(
            payload,
            output_dir=output_dir,
        )
        return {
            **published,
            "expected": v1_reference["ranked"]["expected"],
            "early": v1_reference["ranked"]["early"],
            "top30": top30,
            "ranked_pool": ranked_pool,
        }
    return {
        "trade_date": config.trade_date,
        "paths": {},
        "evidence": validated_evidence,
        "expected": v1_reference["ranked"]["expected"],
        "early": v1_reference["ranked"]["early"],
        "scores": activation_scored,
        "exclusions": exclusions,
        "coverage": coverage,
        "top20": top20,
        "top30": top30,
        "reserve": reserve,
        "ranked_pool": ranked_pool,
        "preaudit": preaudit,
        "comparison": comparison,
        "report": _render_report(
            config.trade_date,
            top20,
            reserve,
            preaudit,
            comparison,
            exclusions,
            coverage,
            activation_scored,
        ),
    }


def build_consumer_oversold_weekly_from_frames(
    *,
    frames: dict[str, pd.DataFrame],
    evidence: pd.DataFrame,
    config: ConsumerOversoldConfig,
    output_dir: str | Path | None = None,
    preaudit_only: bool = False,
) -> dict[str, Any]:
    """Compose the weekly consumer oversold research pipeline from in-memory frames."""
    copied = _copy_frames(frames)
    if not isinstance(evidence, pd.DataFrame):
        raise TypeError("evidence must be a pandas DataFrame")
    evidence_input = evidence.copy(deep=True)

    universe = build_consumer_universe_from_frames(
        assets=copied["assets"],
        statuses=copied["statuses"],
        liquidity=copied["liquidity"],
        industries=copied["industries"],
        industry_rules=copied["industry_rules"],
        asset_overrides=copied["asset_overrides"],
        config=config,
    )
    universe = _normalize_asset_ids(universe, "universe")
    included = universe.loc[universe["included"].astype(bool)].copy()
    membership = included.loc[:, ["asset_id", "consumer_subindustry"]].copy()

    if included.empty:
        validated_evidence = validate_repair_evidence(
            evidence_input, trade_date=config.trade_date
        )
        universe_exclusions = universe.loc[~universe["included"].astype(bool)].rename(
            columns={"name": "stock_name", "exclude_reasons": "exclusion_reasons"}
        )
        universe_exclusions["exclusion_stage"] = "universe"
        exclusions = universe_exclusions.reindex(columns=EXCLUSION_ID_COLUMNS).reset_index(
            drop=True
        )
        empty_scores = pd.DataFrame(
            columns=[
                "asset_id",
                "price_history_complete",
                "return_6m",
                "max_drawdown_12m",
                "relative_return_coverage",
                "relative_return_6m",
                "oversold_score",
                "hard_risk_triggered",
                "hard_risk_review_unknown",
                "evidence_complete",
                "base_upside",
                "pessimistic_scenario_market_cap",
                "base_scenario_market_cap",
                "optimistic_scenario_market_cap",
            ]
        )
        if config.ranking_version == "v2":
            empty_scores = empty_scores.reindex(
                columns=[
                    *empty_scores.columns,
                    "composite_score",
                    "ranking_version",
                    "activation_score",
                    "activation_coverage",
                    "activation_eligible",
                    "activation_exclusion_reasons",
                ]
            )
        coverage = _coverage(
            raw_assets=copied["assets"],
            included=included,
            scores=empty_scores,
            evidence=validated_evidence,
            bars=copied["bars"],
            finance=copied["finance"],
            valuation_history=copied["valuation_history"],
            expected=empty_scores,
            early=empty_scores,
            config=config,
            warnings=[],
        )
        empty_unified = (
            _empty_v2_frame()
            if config.ranking_version == "v2"
            else _empty_unified_frame()
        )
        empty_preaudit = pd.DataFrame(
            columns=(
                V2_PREAUDIT_OUTPUT_COLUMNS
                if config.ranking_version == "v2"
                else PREAUDIT_OUTPUT_COLUMNS
            )
        )
        empty_comparison = pd.DataFrame(
            columns=(
                V2_COMPARISON_COLUMNS
                if config.ranking_version == "v2"
                else COMPARISON_COLUMNS
            )
        )
        coverage["funnel"].update(
            {
                "full": 0,
                "automatic": 0,
                "preaudit": 0,
                "evidence_reviewed": 0,
                "elasticity_complete": 0,
                "final": 0,
                "reserve": 0,
            }
        )
        coverage["unified_funnel"] = {
            "full": 0,
            "automatic": 0,
            "preaudit": 0,
            "evidence_reviewed": 0,
            "evidence_complete": 0,
            "elasticity_complete": 0,
            "final": 0,
            "reserve": 0,
        }
        coverage["publication_status"] = (
            "preaudit_only" if preaudit_only else "coverage_insufficient"
        )
        coverage["warnings"] = [
            f"evidence_complete_pool_below_{config.minimum_evidence_complete}"
        ]
        if config.ranking_version == "v2" and not preaudit_only:
            coverage["warnings"].append("v2_ranked_pool_below_30")
        _add_publication_thresholds(coverage, config)
        if config.ranking_version == "v2":
            coverage.update(
                ranking_version="v2",
                v2_ranked_pool_count=0,
                v2_top30_count=0,
                v2_thresholds={
                    "min_6m_return": config.min_6m_return,
                    "min_12m_drawdown": config.min_12m_drawdown,
                    "min_relative_return": config.min_relative_return,
                    "min_base_upside": config.min_base_upside,
                    "min_composite_score": config.v2_min_composite_score,
                    "min_technical_readiness_score": config.v2_min_technical_readiness_score,
                },
                v2_rank_weights={
                    "repair": config.v2_repair_rank_weight,
                    "activation": config.v2_activation_rank_weight,
                },
                v2_activation_weights={
                    "technical_readiness": config.technical_readiness_weight,
                    "continuation_character": config.continuation_character_weight,
                    "residual_price_space": config.residual_price_space_weight,
                    "capital_efficiency": config.capital_efficiency_weight,
                    "catalyst_timing": config.catalyst_timing_weight,
                },
                activation_funnel={
                    "first_gate_eligible": 0,
                    "activation_covered": 0,
                    "activation_eligible": 0,
                    "ranked_pool": 0,
                    "top20": 0,
                    "top30": 0,
                    "reserve": 0,
                },
            )
        payload = {
            "trade_date": config.trade_date,
            "evidence": validated_evidence,
            "scores": empty_scores,
            "exclusions": exclusions,
            "coverage": coverage,
            "top20": empty_unified.copy(),
            "reserve": empty_unified.copy(),
            "preaudit": empty_preaudit.copy(),
            "comparison": empty_comparison.copy(),
        }
        if config.ranking_version == "v2":
            payload["top30"] = empty_unified.copy()
            payload["ranked_pool"] = empty_unified.copy()
        if output_dir is not None:
            published = write_consumer_oversold_artifacts(payload, output_dir=output_dir)
            return {
                **published,
                "expected": empty_scores.copy(),
                "early": empty_scores.copy(),
                "coverage": coverage,
                **(
                    {
                        "top30": empty_unified.copy(),
                        "ranked_pool": empty_unified.copy(),
                    }
                    if config.ranking_version == "v2"
                    else {}
                ),
            }
        return {
            "paths": {},
            **{
                key: payload[key]
                for key in ("evidence", "scores", "exclusions", "coverage")
            },
            "expected": empty_scores.copy(),
            "early": empty_scores.copy(),
            "top20": empty_unified.copy(),
            "reserve": empty_unified.copy(),
            "preaudit": empty_preaudit.copy(),
            "comparison": empty_comparison,
            **(
                {
                    "top30": empty_unified.copy(),
                    "ranked_pool": empty_unified.copy(),
                }
                if config.ranking_version == "v2"
                else {}
            ),
            "report": _render_report(
                config.trade_date,
                empty_unified,
                empty_unified,
                empty_preaudit,
                empty_comparison,
                exclusions,
                coverage,
                empty_scores,
            ),
        }

    _require_downstream_columns(copied)

    included_ids = set(included["asset_id"])
    bars = copied["bars"].loc[copied["bars"]["asset_id"].astype(str).isin(included_ids)].copy()
    share_capacity = copied["share_capacity"].loc[
        copied["share_capacity"]["asset_id"].astype(str).isin(included_ids)
    ].copy()
    finance = copied["finance"].loc[copied["finance"]["asset_id"].astype(str).isin(included_ids)].copy()
    finance = finance.loc[
        finance["report_period"].notna() & finance["announcement_date"].notna()
    ].copy()
    price = compute_price_features(bars, membership, trade_date=config.trade_date)
    residual = compute_residual_price_features(bars, trade_date=config.trade_date)
    stock_bars = bars.drop(columns=["stock_code"], errors="ignore").merge(
        included.loc[:, ["asset_id", "stock_code"]],
        on="asset_id",
        how="inner",
        validate="many_to_one",
    )
    stock_character = compute_stock_character_features(
        stock_bars, trade_date=config.trade_date
    )
    capacity = compute_market_capacity_features(
        bars, share_capacity, trade_date=config.trade_date
    )
    fundamentals = compute_fundamental_features(finance, trade_date=config.trade_date)

    completed = None
    if "repair_already_completed" in evidence_input.columns:
        completed = evidence_input.loc[:, ["asset_id", "repair_already_completed"]].copy()
        completed = _normalize_asset_ids(completed, "repair_evidence")
    validated_evidence = validate_repair_evidence(evidence_input, trade_date=config.trade_date)
    if completed is not None:
        validated_evidence = _merge_one_to_one(validated_evidence, completed, "repair_evidence_completed")
    manual = validated_evidence.loc[
        :,
        [
            "asset_id",
            "audit_review_status",
            "pledge_debt_review_status",
            "permanent_impairment_status",
        ],
    ]
    risk = compute_hard_risk_features(fundamentals, manual)
    automatic_risk = compute_hard_risk_features(fundamentals, None).rename(
        columns={"hard_risk_triggered": "automatic_hard_risk_triggered"}
    )
    automatic_risk = automatic_risk.drop(
        columns=[
            "hard_risk_codes",
            "hard_risk_review_unknown",
            "automated_risk_review_unknown",
        ],
        errors="ignore",
    )

    current_valuation_input = _normalize_asset_ids(
        copied["current_valuation"], "current_valuation"
    )
    current_valuation_input = current_valuation_input.drop(
        columns=["current_total_market_cap"], errors="ignore"
    ).merge(
        capacity.loc[:, ["asset_id", "current_total_market_cap"]],
        on="asset_id",
        how="left",
        validate="one_to_one",
    )
    current_valuation_input["current_market_cap"] = current_valuation_input[
        "current_total_market_cap"
    ]
    current, valuation_history, valuation_fundamentals, warnings = _prepare_valuation_inputs(
        current_valuation_input,
        copied["valuation_history"],
        fundamentals,
        membership,
        config.trade_date,
    )
    valuation = compute_valuation_features(
        current, valuation_history, valuation_fundamentals
    ).rename(
        columns={
            f"{scenario}_market_cap": f"{scenario}_scenario_market_cap"
            for scenario in ("pessimistic", "base", "optimistic")
        }
    )

    candidates = included.rename(columns={"name": "stock_name"})
    candidates = _merge_one_to_one(
        candidates,
        price.drop(columns=["consumer_subindustry"], errors="ignore"),
        "price_features",
    )
    candidates = _merge_one_to_one(
        candidates,
        residual.drop(
            columns=["latest_trade_date", "history_sessions", "rebound_from_low_60d"],
            errors="ignore",
        ),
        "residual_price_features",
    )
    candidates = _merge_one_to_one(
        candidates,
        stock_character.drop(columns=["history_sessions"], errors="ignore"),
        "stock_character_features",
    )
    candidates = _merge_one_to_one(
        candidates,
        capacity.drop(columns=["latest_trade_date", "history_sessions"], errors="ignore"),
        "market_capacity_features",
    )
    candidates = _merge_one_to_one(candidates, fundamentals, "fundamental_features")
    candidates = _merge_one_to_one(candidates, risk, "hard_risk_features")
    candidates = _merge_one_to_one(
        candidates, automatic_risk, "automatic_hard_risk_features"
    )
    candidates = _merge_one_to_one(candidates, valuation, "valuation_features")
    evidence_for_merge = validated_evidence.drop(
        columns=["hard_risk_review_unknown"], errors="ignore"
    ).rename(columns={"stock_code": "stock_code_evidence"})
    candidates = _merge_one_to_one(candidates, evidence_for_merge, "validated_evidence")
    candidates = _empty_evidence_defaults(candidates)
    for column, default in (
        ("hard_risk_triggered", False),
        ("hard_risk_review_unknown", True),
        ("automated_risk_review_unknown", True),
    ):
        if column not in candidates:
            candidates[column] = default
        candidates[column] = candidates[column].fillna(default).astype(bool)
    if "hard_risk_codes" not in candidates:
        candidates["hard_risk_codes"] = "hard_risk_review_unknown"
    candidates["hard_risk_codes"] = candidates["hard_risk_codes"].fillna(
        "hard_risk_review_unknown"
    )

    priced_rows = []
    for _, row in candidates.iterrows():
        priced_rows.append(
            compute_already_priced_features(
                row,
                row,
                evidence_revision_state=str(row.get("forecast_revision_state", "")),
            )
        )
    priced = pd.DataFrame(priced_rows, index=candidates.index)
    candidates = pd.concat([candidates, priced], axis=1)
    candidates["oversold_score"] = compute_oversold_score(candidates)
    scored = score_candidates(candidates, config)
    if config.ranking_version == "v2":
        return _build_v2_result(
            copied=copied,
            universe=universe,
            included=included,
            membership=membership,
            bars=bars,
            finance=finance,
            valuation_history=valuation_history,
            validated_evidence=validated_evidence,
            scored=scored,
            config=config,
            warnings=warnings,
            output_dir=output_dir,
            preaudit_only=preaudit_only,
        )
    gated = apply_candidate_gates(scored, config)
    automatically_gated = _apply_automatic_gates(gated, config)
    elasticity_scored = score_rebound_elasticity(automatically_gated, config)
    ranked = rank_candidate_buckets(elasticity_scored, config)
    elasticity_scored["preaudit_score"] = (
        0.30 * elasticity_scored["oversold_score"]
        + 0.25 * elasticity_scored["valuation_repair_score"]
        + 0.20 * elasticity_scored["operating_gap_score"]
        + 0.15 * elasticity_scored["balance_sheet_score"]
        + 0.10 * elasticity_scored["automatic_elasticity_score"]
    ).where(
        elasticity_scored["automatic_eligible"]
        & elasticity_scored["automatic_elasticity_coverage"]
    )
    preaudit_full = elasticity_scored.loc[
        elasticity_scored["preaudit_score"].notna()
    ].sort_values(
        ["preaudit_score", "oversold_score", "asset_id"],
        ascending=[False, False, True],
        kind="stable",
    ).head(config.preaudit_size).reset_index(drop=True)
    preaudit_ids = set(preaudit_full["asset_id"].astype(str))
    preaudit = preaudit_full.reindex(columns=PREAUDIT_OUTPUT_COLUMNS)

    final_scored = score_rebound_elasticity(
        automatically_gated.loc[
            automatically_gated["asset_id"].isin(preaudit_ids)
        ].copy(),
        config,
    )
    unified = (
        _empty_unified_frame()
        if preaudit_only
        else rank_unified_candidates(final_scored, config)
    )
    final_score_columns = (
        "residual_deviation_component_coverage",
        "residual_deviation_score",
        "stock_character_component_coverage",
        "stock_character_score",
        "market_capacity_component_coverage",
        "market_capacity_score",
        "catalyst_liquidity_coverage",
        "catalyst_liquidity_score",
        "elasticity_coverage",
        "elasticity_score",
    )
    final_scores_by_asset = final_scored.set_index("asset_id")
    for field in final_score_columns:
        elasticity_scored[field] = elasticity_scored["asset_id"].map(
            final_scores_by_asset[field]
        )

    reviewed_evidence_ids = set(validated_evidence["asset_id"].astype(str))
    complete_evidence_ids = set(
        validated_evidence.loc[
            validated_evidence["evidence_complete"].fillna(False).astype(bool),
            "asset_id",
        ].astype(str)
    )
    preaudit_evidence_reviewed = len(preaudit_ids & reviewed_evidence_ids)
    preaudit_evidence_complete = len(preaudit_ids & complete_evidence_ids)
    full_pool_evidence_complete = int(
        elasticity_scored["evidence_complete"].fillna(False).astype(bool).sum()
    )
    required_ranked = config.final_top_n + config.reserve_top_n
    publication_warnings: list[str] = []
    if preaudit_evidence_complete < config.minimum_evidence_complete:
        publication_warnings.append(
            f"evidence_complete_pool_below_{config.minimum_evidence_complete}"
        )
    if not preaudit_only and len(unified) < required_ranked:
        publication_warnings.append(f"ranked_pool_below_{required_ranked}")
    publication_status = (
        "preaudit_only"
        if preaudit_only
        else "ready" if not publication_warnings else "coverage_insufficient"
    )
    if publication_status == "ready":
        top20 = unified.loc[unified["final_rank"].le(config.final_top_n)].copy()
        reserve = unified.loc[
            unified["final_rank"].gt(config.final_top_n)
            & unified["final_rank"].le(required_ranked)
        ].copy()
    else:
        top20 = unified.iloc[0:0].copy()
        reserve = unified.iloc[0:0].copy()
    top20 = top20.reindex(columns=UNIFIED_OUTPUT_COLUMNS)
    reserve = reserve.reindex(columns=UNIFIED_OUTPUT_COLUMNS)
    comparison = _build_rank_comparison(elasticity_scored, ranked, unified)

    universe_exclusions = universe.loc[~universe["included"].astype(bool)].rename(
        columns={
            "name": "stock_name",
            "exclude_reasons": "exclusion_reasons",
        }
    )
    universe_exclusions["exclusion_stage"] = "universe"
    universe_exclusions = universe_exclusions.reindex(columns=EXCLUSION_ID_COLUMNS)
    gate_exclusions = elasticity_scored.loc[~elasticity_scored["eligible"]].copy()
    gate_exclusions["exclusion_stage"] = "gate"
    gate_columns = [
        *EXCLUSION_ID_COLUMNS,
        *[
            column
            for column in elasticity_scored.columns
            if column not in EXCLUSION_ID_COLUMNS
        ],
    ]
    gate_exclusions = gate_exclusions.reindex(columns=gate_columns)
    exclusions = pd.concat([universe_exclusions, gate_exclusions], ignore_index=True, sort=False)
    exclusions = exclusions.sort_values(
        ["exclusion_stage", "asset_id"], kind="stable"
    ).reset_index(drop=True)

    coverage = _coverage(
        raw_assets=copied["assets"],
        included=included,
        scores=elasticity_scored,
        evidence=validated_evidence,
        bars=bars,
        finance=finance,
        valuation_history=valuation_history,
        expected=ranked["expected"],
        early=ranked["early"],
        config=config,
        warnings=[*warnings, *publication_warnings],
    )
    unified_funnel = {
        "full": int(len(elasticity_scored)),
        "automatic": int(elasticity_scored["automatic_eligible"].sum()),
        "preaudit": int(len(preaudit)),
        "evidence_reviewed": int(preaudit_evidence_reviewed),
        "evidence_complete": int(preaudit_evidence_complete),
        "elasticity_complete": int(
            elasticity_scored.loc[
                elasticity_scored["asset_id"].isin(preaudit_ids)
                & elasticity_scored["elasticity_coverage"].astype(bool),
                "asset_id",
            ].nunique()
        ),
        "final": int(len(top20)),
        "reserve": int(len(reserve)),
    }
    coverage["unified_funnel"] = unified_funnel
    coverage["full_pool_evidence_complete"] = full_pool_evidence_complete
    coverage["funnel"].update(
        {
            key: value
            for key, value in unified_funnel.items()
            if key != "evidence_complete"
        }
    )
    coverage["publication_status"] = publication_status
    coverage["warnings"] = sorted(set([*coverage["warnings"], *publication_warnings]))
    _add_publication_thresholds(coverage, config)
    payload = {
        "trade_date": config.trade_date,
        "evidence": validated_evidence,
        "scores": elasticity_scored,
        "exclusions": exclusions,
        "coverage": coverage,
        "top20": top20,
        "reserve": reserve,
        "preaudit": preaudit,
        "comparison": comparison,
    }
    if output_dir is not None:
        published = write_consumer_oversold_artifacts(payload, output_dir=output_dir)
        return {
            **published,
            "expected": ranked["expected"],
            "early": ranked["early"],
            "coverage": coverage,
        }
    return {
        "paths": {},
        "evidence": validated_evidence,
        "expected": ranked["expected"],
        "early": ranked["early"],
        "scores": elasticity_scored,
        "exclusions": exclusions,
        "coverage": coverage,
        "top20": top20,
        "reserve": reserve,
        "preaudit": preaudit,
        "comparison": comparison,
        "report": _render_report(
            config.trade_date,
            top20,
            reserve,
            preaudit,
            comparison,
            exclusions,
            coverage,
            elasticity_scored,
        ),
    }


def _positive(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) and number > 0.0 else math.nan


def _current_valuation_from_histories(
    valuation_history: pd.DataFrame,
    fundamentals: pd.DataFrame,
    membership: pd.DataFrame,
    latest_raw_close: pd.Series,
    total_share: pd.Series,
    trade_date: str,
) -> pd.DataFrame:
    history = valuation_history.copy(deep=True)
    if history.empty:
        latest = pd.DataFrame(columns=["asset_id", "pe_ttm", "ps_ttm", "ev_ebitda"])
    else:
        history["valuation_date"] = pd.to_datetime(history["valuation_date"], errors="coerce")
        history = history.loc[history["valuation_date"].le(pd.Timestamp(trade_date))]
        latest = history.sort_values(["asset_id", "valuation_date"], kind="stable").drop_duplicates(
            "asset_id", keep="last"
        )
    latest_fundamental = fundamentals.set_index("asset_id") if not fundamentals.empty else pd.DataFrame()
    valuation_by_asset = latest.set_index("asset_id") if not latest.empty else pd.DataFrame()
    rows: list[dict[str, object]] = []
    for member in membership.itertuples(index=False):
        asset_id = str(member.asset_id)
        valuation = valuation_by_asset.loc[asset_id] if asset_id in valuation_by_asset.index else {}
        fundamental = (
            latest_fundamental.loc[asset_id]
            if isinstance(latest_fundamental, pd.DataFrame) and asset_id in latest_fundamental.index
            else {}
        )
        pe = _positive(valuation.get("pe_ttm", math.nan))
        ps = _positive(valuation.get("ps_ttm", math.nan))
        ev = _positive(valuation.get("ev_ebitda", math.nan))
        revenue = _positive(fundamental.get("latest_revenue_ttm", math.nan))
        profit = _positive(fundamental.get("latest_np_parent_ttm", math.nan))
        close = _positive(latest_raw_close.get(asset_id, math.nan))
        shares = _positive(total_share.get(asset_id, math.nan))
        market_cap = close * shares if math.isfinite(close) and math.isfinite(shares) else math.nan
        rows.append(
            {
                "asset_id": asset_id,
                "as_of_date": trade_date,
                "consumer_subindustry": member.consumer_subindustry,
                "current_market_cap": market_cap,
                "net_debt": math.nan,
                "pe_ttm": pe,
                "ps_ttm": ps,
                "ev_ebitda": ev,
                "revenue_ttm": revenue,
                "np_parent_ttm": profit,
                "ebitda_ttm": math.nan,
            }
        )
    return pd.DataFrame(rows, columns=CURRENT_VALUATION_COLUMNS)


def run_consumer_oversold_weekly(
    *,
    trade_date: str,
    evidence_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
    preaudit_only: bool = False,
    ranking_version: str = "v1",
    evidence_reconstruction_mode: str | None = None,
    evidence_information_cutoff: str | None = None,
) -> dict[str, Any]:
    """Load point-in-time database inputs and publish the weekly pipeline."""
    config = ConsumerOversoldConfig(
        trade_date=trade_date, ranking_version=ranking_version
    )
    reconstruction_requested = (
        evidence_reconstruction_mode is not None
        or evidence_information_cutoff is not None
    )
    if (
        ranking_version == "v2"
        and trade_date == RETROSPECTIVE_EVIDENCE_TRADE_DATE
        and (
            evidence_reconstruction_mode is None
            or evidence_information_cutoff is None
        )
    ):
        raise ValueError(
            "frozen 2026-07-27 v2 requires retrospective_point_in_time "
            "evidence reconstruction parameters"
        )
    evidence_file = Path(evidence_path).expanduser()
    if not evidence_file.is_file():
        raise FileNotFoundError(f"evidence path does not exist: {evidence_file}")
    evidence = pd.read_csv(evidence_file, dtype={"stock_code": "string"})
    reconstruction_provenance: dict[str, str] = {}
    if reconstruction_requested:
        reconstruction_provenance = validate_retrospective_evidence_publications(
            evidence,
            ranking_version=ranking_version,
            trade_date=trade_date,
            reconstruction_mode=evidence_reconstruction_mode,
            information_cutoff=evidence_information_cutoff,
        )
        evidence = evidence.copy(deep=True)
        evidence["evidence_as_of_date"] = reconstruction_provenance[
            "evidence_information_cutoff"
        ]
    industry_rules = pd.read_csv(INDUSTRY_RULES_PATH)
    asset_overrides = pd.read_csv(ASSET_OVERRIDES_PATH, dtype={"stock_code": "string"})

    universe_frames = load_consumer_universe_frames(trade_date, service=service)
    universe = build_consumer_universe_from_frames(
        **universe_frames,
        industry_rules=industry_rules,
        asset_overrides=asset_overrides,
        config=config,
    )
    included = universe.loc[universe["included"].astype(bool), ["asset_id", "consumer_subindustry"]]
    asset_ids = included["asset_id"].astype(str).tolist()
    bars = load_consumer_market_history(trade_date, service=service, asset_ids=asset_ids)
    share_capacity = load_consumer_share_capacity(
        asset_ids, trade_date, service=service
    )
    finance_with_shares = load_consumer_finance_history(asset_ids, trade_date, service=service)
    valuation_raw = load_consumer_valuation_history(asset_ids, trade_date, service=service)
    if "total_share" in share_capacity.columns:
        total_share = share_capacity.set_index("asset_id")["total_share"]
    else:
        total_share = pd.Series(dtype=float)
    finance = finance_with_shares.loc[
        finance_with_shares.get("report_period", pd.Series(index=finance_with_shares.index, dtype=object)).notna()
        & finance_with_shares.get("announcement_date", pd.Series(index=finance_with_shares.index, dtype=object)).notna()
    ].copy()
    fundamentals = compute_fundamental_features(finance, trade_date=trade_date)
    if bars.empty or "raw_close" not in bars.columns:
        latest_raw_close = pd.Series(dtype=float)
    else:
        market = bars.copy(deep=True)
        market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce")
        market = market.loc[market["trade_date"].le(pd.Timestamp(trade_date))]
        latest_raw_close = market.sort_values(["asset_id", "trade_date"], kind="stable").drop_duplicates(
            "asset_id", keep="last"
        ).set_index("asset_id")["raw_close"]
    valuation_history = valuation_raw.copy(deep=True)
    for column in VALUATION_HISTORY_COLUMNS:
        if column not in valuation_history.columns:
            valuation_history[column] = pd.Series(dtype=object)
    membership_map = included.set_index("asset_id")["consumer_subindustry"]
    if not valuation_history.empty:
        valuation_history["asset_id"] = valuation_history["asset_id"].astype(str)
        valuation_history["consumer_subindustry"] = valuation_history["asset_id"].map(membership_map)
    valuation_history = valuation_history.loc[:, VALUATION_HISTORY_COLUMNS]
    current_valuation = _current_valuation_from_histories(
        valuation_history,
        fundamentals,
        included,
        latest_raw_close,
        total_share,
        trade_date,
    )
    frames = {
        **universe_frames,
        "industry_rules": industry_rules,
        "asset_overrides": asset_overrides,
        "bars": bars,
        "share_capacity": share_capacity,
        "finance": finance,
        "current_valuation": current_valuation,
        "valuation_history": valuation_history,
    }
    payload = build_consumer_oversold_weekly_from_frames(
        frames=frames,
        evidence=evidence,
        config=config,
        output_dir=None if reconstruction_requested else output_dir,
        preaudit_only=preaudit_only,
    )
    if not reconstruction_requested:
        return payload
    payload["coverage"] = {
        **payload["coverage"],
        **reconstruction_provenance,
    }
    return write_consumer_oversold_artifacts(payload, output_dir=output_dir)
