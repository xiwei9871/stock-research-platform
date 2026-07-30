from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS

from .contracts import ConsumerOversoldConfig
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
from .reporting import _render_report, write_consumer_oversold_artifacts
from .scoring import (
    apply_candidate_gates,
    rank_candidate_buckets,
    rank_unified_candidates,
    score_candidates,
)
from .universe import build_consumer_universe_from_frames


INDUSTRY_RULES_PATH = SETTINGS.repo_root / "config" / "consumer_oversold_industry_rules_v1.csv"
ASSET_OVERRIDES_PATH = SETTINGS.repo_root / "config" / "consumer_oversold_asset_overrides_v1.csv"

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


def _empty_unified_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIFIED_OUTPUT_COLUMNS)


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
    oversold_pass = (
        price_pass
        & scores["relative_return_6m"].le(config.min_relative_return)
        & scores["oversold_score"].ge(config.min_oversold_score)
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
        "oversold_score_below_threshold": result["oversold_score"].ge(
            config.min_oversold_score
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
    new_rank = (
        unified.set_index("asset_id")["final_rank"]
        if not unified.empty
        else pd.Series(dtype=float)
    )
    comparison["old_bucket_rank"] = comparison["asset_id"].map(bucket_rank)
    comparison["old_combined_rank"] = comparison["asset_id"].map(old_combined)
    comparison["new_rank"] = comparison["asset_id"].map(new_rank)
    comparison["rank_change"] = (
        comparison["old_combined_rank"] - comparison["new_rank"]
    )
    return comparison.reindex(columns=COMPARISON_COLUMNS).sort_values(
        "asset_id", kind="stable"
    ).reset_index(drop=True)


def build_consumer_oversold_weekly_from_frames(
    *,
    frames: dict[str, pd.DataFrame],
    evidence: pd.DataFrame,
    config: ConsumerOversoldConfig,
    output_dir: str | Path | None = None,
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
        empty_unified = _empty_unified_frame()
        empty_preaudit = pd.DataFrame(columns=PREAUDIT_OUTPUT_COLUMNS)
        empty_comparison = pd.DataFrame(columns=COMPARISON_COLUMNS)
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
        coverage["publication_status"] = "coverage_insufficient"
        coverage["warnings"] = [
            f"evidence_complete_pool_below_{config.minimum_evidence_complete}"
        ]
        _add_publication_thresholds(coverage, config)
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
        if output_dir is not None:
            published = write_consumer_oversold_artifacts(payload, output_dir=output_dir)
            return {
                **published,
                "expected": empty_scores.copy(),
                "early": empty_scores.copy(),
                "coverage": coverage,
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
    unified = rank_unified_candidates(final_scored, config)
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
    if len(unified) < required_ranked:
        publication_warnings.append(f"ranked_pool_below_{required_ranked}")
    publication_status = "ready" if not publication_warnings else "coverage_insufficient"
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
) -> dict[str, Any]:
    """Load point-in-time database inputs and publish the weekly pipeline."""
    config = ConsumerOversoldConfig(trade_date=trade_date)
    evidence_file = Path(evidence_path).expanduser()
    if not evidence_file.is_file():
        raise FileNotFoundError(f"evidence path does not exist: {evidence_file}")
    evidence = pd.read_csv(evidence_file, dtype={"stock_code": "string"})
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
    return build_consumer_oversold_weekly_from_frames(
        frames=frames,
        evidence=evidence,
        config=config,
        output_dir=output_dir,
    )
