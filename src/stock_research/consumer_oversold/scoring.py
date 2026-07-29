from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd

from .contracts import EARLY_VALIDATION, EXPECTED_REPAIR, ConsumerOversoldConfig


STRICT_NUMERIC_TYPES = (int, float, np.integer, np.floating, Decimal)


SCORE_REQUIRED_COLUMNS = (
    "asset_id",
    "consumer_subindustry",
    "latest_net_margin",
    "normal_net_margin",
    "latest_roe",
    "normal_roe",
    "latest_revenue_growth",
    "normal_revenue_growth",
    "expected_improvement_score",
    "catalyst_verifiability_score",
    "valuation_depression_percentile",
    "base_upside",
    "latest_equity_parent",
    "latest_debt_ratio",
    "latest_ocf_to_np",
    "latest_operating_cash_flow",
    "prior_operating_cash_flow",
    "second_prior_operating_cash_flow",
    "oversold_score",
    "priced_in_penalty",
)
SCORE_NUMERIC_COLUMNS = SCORE_REQUIRED_COLUMNS[2:]
SCORE_ADDED_COLUMNS = (
    "operating_gap_score",
    "equity_score",
    "debt_ratio_percentile",
    "debt_score",
    "ocf_quality_score",
    "cash_trend_score",
    "balance_sheet_component_count",
    "balance_sheet_coverage",
    "balance_sheet_score",
    "base_upside_percentile",
    "valuation_repair_score",
    "repair_potential_score",
    "composite_score",
)

GATE_REQUIRED_COLUMNS = (
    "asset_id",
    "included",
    "return_6m",
    "max_drawdown_12m",
    "relative_return_6m",
    "oversold_score",
    "base_upside",
    "evidence_complete",
    "hard_risk_triggered",
    "hard_risk_review_unknown",
    "balance_sheet_coverage",
    "repair_bucket",
    "latest_revenue_growth",
    "normal_revenue_growth",
    "latest_profit_growth",
    "normal_profit_growth",
    "latest_net_margin",
    "normal_net_margin",
    "composite_score",
)
GATE_NUMERIC_COLUMNS = (
    "return_6m",
    "max_drawdown_12m",
    "relative_return_6m",
    "oversold_score",
    "base_upside",
    "latest_revenue_growth",
    "normal_revenue_growth",
    "latest_profit_growth",
    "normal_profit_growth",
    "latest_net_margin",
    "normal_net_margin",
    "composite_score",
)
GATE_BOOLEAN_COLUMNS = (
    "included",
    "evidence_complete",
    "hard_risk_triggered",
    "hard_risk_review_unknown",
    "balance_sheet_coverage",
)
RANK_REQUIRED_COLUMNS = (
    "asset_id",
    "repair_bucket",
    "eligible",
    "composite_score",
    "base_upside",
)


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _supply_empty_schema(frame: pd.DataFrame, required: tuple[str, ...]) -> pd.DataFrame:
    if not frame.empty:
        return frame
    missing = [column for column in required if column not in frame.columns]
    if not missing:
        return frame
    return frame.reindex(columns=[*frame.columns, *missing])


def _prepare_assets(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    result = frame.copy()
    missing = result["asset_id"].isna()
    normalized = result["asset_id"].astype(str).str.strip()
    invalid = missing | normalized.eq("")
    if invalid.any():
        raise ValueError(f"{name} asset_id must be non-empty")
    result["asset_id"] = normalized
    duplicate = result["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = result.loc[duplicate, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"{name} contains duplicate asset_id {asset_id}")
    return result


def _is_missing(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    return isinstance(value, (float, np.floating)) and math.isnan(float(value))


def _assign_numeric(frame: pd.DataFrame, fields: tuple[str, ...], name: str) -> None:
    for field in fields:
        parsed: list[float] = []
        for index, value in frame[field].items():
            if _is_missing(value):
                parsed.append(math.nan)
                continue
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, STRICT_NUMERIC_TYPES
            ):
                raise ValueError(
                    f"{name} asset {frame.at[index, 'asset_id']} field {field} must be finite numeric"
                )
            try:
                number = float(value)
            except (OverflowError, ValueError):
                raise ValueError(
                    f"{name} asset {frame.at[index, 'asset_id']} field {field} must be finite numeric"
                ) from None
            if not math.isfinite(number):
                raise ValueError(
                    f"{name} asset {frame.at[index, 'asset_id']} field {field} must be finite numeric"
                )
            parsed.append(number)
        frame[field] = parsed


def _validate_range(
    frame: pd.DataFrame, field: str, lower: float, upper: float, name: str
) -> None:
    invalid = frame[field].notna() & ~frame[field].between(lower, upper, inclusive="both")
    if invalid.any():
        asset_id = frame.loc[invalid, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(
            f"{name} asset {asset_id} field {field} must be between {lower:g} and {upper:g}"
        )


def _mean_available(values: list[float], minimum: int) -> float:
    available = [value for value in values if not math.isnan(value)]
    if len(available) < minimum:
        return math.nan
    return float(np.mean(available))


def _gap(latest: float, normal: float, denominator_floor: float) -> float:
    if math.isnan(latest) or math.isnan(normal):
        return math.nan
    return float(np.clip((normal - latest) / max(abs(normal), denominator_floor), 0.0, 1.0))


def _revenue_growth_gap(latest: float, normal: float) -> float:
    if math.isnan(latest) or math.isnan(normal):
        return math.nan
    return float(np.clip((normal - latest) / 0.30, 0.0, 1.0))


def _cash_trend(latest: float, prior: float, second_prior: float) -> float:
    if any(math.isnan(value) for value in (latest, prior, second_prior)):
        return math.nan
    if latest >= prior >= second_prior:
        return 100.0
    if latest >= prior:
        return 60.0
    if latest > 0.0:
        return 30.0
    return 0.0


def _at_least_ninety_percent(latest: float, normal: float) -> bool:
    threshold = 0.9 * normal
    return latest >= threshold or math.isclose(latest, threshold, rel_tol=1e-12, abs_tol=1e-15)


def score_candidates(rows: pd.DataFrame, config: ConsumerOversoldConfig) -> pd.DataFrame:
    """Compute approved consumer-repair component and composite scores."""
    rows = _supply_empty_schema(rows, SCORE_REQUIRED_COLUMNS)
    _require_columns(rows, SCORE_REQUIRED_COLUMNS, "rows")
    frame = _prepare_assets(rows, "rows")
    invalid_industry = frame["consumer_subindustry"].isna() | frame[
        "consumer_subindustry"
    ].astype(str).str.strip().eq("")
    if invalid_industry.any():
        asset_id = frame.loc[invalid_industry, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(
            f"rows asset {asset_id} field consumer_subindustry must be non-empty"
        )
    _assign_numeric(frame, SCORE_NUMERIC_COLUMNS, "rows")
    _validate_range(frame, "expected_improvement_score", 0.0, 100.0, "rows")
    _validate_range(frame, "catalyst_verifiability_score", 0.0, 100.0, "rows")
    _validate_range(frame, "valuation_depression_percentile", 0.0, 1.0, "rows")
    _validate_range(frame, "oversold_score", 0.0, 100.0, "rows")
    _validate_range(frame, "priced_in_penalty", 0.0, config.max_priced_in_penalty, "rows")

    if frame.empty:
        for column in SCORE_ADDED_COLUMNS:
            frame[column] = pd.Series(dtype="bool" if column == "balance_sheet_coverage" else "float64")
        return frame.sort_values("asset_id", kind="stable").reset_index(drop=True)

    frame["operating_gap_score"] = [
        100.0
        * _mean_available(
            [
                _gap(latest_margin, normal_margin, 0.01),
                _gap(latest_roe, normal_roe, 0.01),
                _revenue_growth_gap(latest_revenue, normal_revenue),
            ],
            2,
        )
        for latest_margin, normal_margin, latest_roe, normal_roe, latest_revenue, normal_revenue in zip(
            frame["latest_net_margin"],
            frame["normal_net_margin"],
            frame["latest_roe"],
            frame["normal_roe"],
            frame["latest_revenue_growth"],
            frame["normal_revenue_growth"],
            strict=True,
        )
    ]
    frame["equity_score"] = np.where(
        frame["latest_equity_parent"].isna(),
        np.nan,
        np.where(frame["latest_equity_parent"].gt(0.0), 100.0, 0.0),
    )

    peer_count = frame.groupby("consumer_subindustry", dropna=False)["latest_debt_ratio"].transform("count")
    debt_percentile = frame.groupby("consumer_subindustry", dropna=False)["latest_debt_ratio"].rank(
        pct=True, ascending=True
    )
    frame["debt_ratio_percentile"] = debt_percentile.where(peer_count.ge(3))
    frame["debt_score"] = 100.0 * (1.0 - frame["debt_ratio_percentile"])
    frame["ocf_quality_score"] = frame["latest_ocf_to_np"].clip(0.0, 1.0) * 100.0
    frame["cash_trend_score"] = [
        _cash_trend(latest, prior, second)
        for latest, prior, second in zip(
            frame["latest_operating_cash_flow"],
            frame["prior_operating_cash_flow"],
            frame["second_prior_operating_cash_flow"],
            strict=True,
        )
    ]
    balance_columns = ["equity_score", "debt_score", "ocf_quality_score", "cash_trend_score"]
    frame["balance_sheet_component_count"] = frame[balance_columns].notna().sum(axis=1)
    frame["balance_sheet_coverage"] = frame["balance_sheet_component_count"].ge(3)
    frame["balance_sheet_score"] = frame[balance_columns].mean(axis=1, skipna=True).where(
        frame["balance_sheet_coverage"]
    )

    valid_upside_count = int(frame["base_upside"].notna().sum())
    frame["base_upside_percentile"] = (
        frame["base_upside"].rank(pct=True, ascending=True)
        if valid_upside_count >= 2
        else math.nan
    )
    frame["valuation_repair_score"] = (
        50.0 * frame["valuation_depression_percentile"]
        + 50.0 * frame["base_upside_percentile"]
    )
    frame["repair_potential_score"] = (
        0.25 * frame["operating_gap_score"]
        + 0.25 * frame["expected_improvement_score"]
        + 0.20 * frame["catalyst_verifiability_score"]
        + 0.15 * frame["balance_sheet_score"]
        + 0.15 * (100.0 * frame["valuation_depression_percentile"])
    )
    frame["composite_score"] = (
        0.35 * frame["repair_potential_score"]
        + 0.25 * frame["valuation_repair_score"]
        + 0.20 * frame["oversold_score"]
        + 0.15 * frame["balance_sheet_score"]
        + 0.05 * frame["catalyst_verifiability_score"]
        - frame["priced_in_penalty"]
    )
    return frame.sort_values("asset_id", kind="stable").reset_index(drop=True)


def _parse_boolean(value: object, field: str, asset_id: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        if int(value) in (0, 1):
            return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true"}:
            return True
        if normalized in {"0", "false"}:
            return False
    raise ValueError(f"rows asset {asset_id} field {field} must be a strict boolean")


def apply_candidate_gates(rows: pd.DataFrame, config: ConsumerOversoldConfig) -> pd.DataFrame:
    """Apply all approved candidate gates while retaining excluded rows."""
    rows = _supply_empty_schema(rows, GATE_REQUIRED_COLUMNS)
    _require_columns(rows, GATE_REQUIRED_COLUMNS, "rows")
    frame = _prepare_assets(rows, "rows")
    _assign_numeric(frame, GATE_NUMERIC_COLUMNS, "rows")
    for field in GATE_BOOLEAN_COLUMNS:
        frame[field] = [
            _parse_boolean(value, field, asset_id)
            for value, asset_id in zip(frame[field], frame["asset_id"], strict=True)
        ]
    explicit_completed = [False] * len(frame)
    if "repair_already_completed" in frame.columns:
        explicit_completed = [
            _parse_boolean(value, "repair_already_completed", asset_id)
            for value, asset_id in zip(
                frame["repair_already_completed"], frame["asset_id"], strict=True
            )
        ]
        frame["repair_already_completed"] = explicit_completed

    eligible_values: list[bool] = []
    reason_values: list[str] = []
    for row, explicitly_completed in zip(
        frame.itertuples(index=False), explicit_completed, strict=True
    ):
        reasons: set[str] = set()
        if not row.included:
            reasons.add("universe_excluded")
        price_passes = (
            not math.isnan(row.return_6m) and row.return_6m <= config.min_6m_return
        ) or (
            not math.isnan(row.max_drawdown_12m)
            and row.max_drawdown_12m <= config.min_12m_drawdown
        )
        if not price_passes:
            reasons.add("price_threshold_not_met")
        if math.isnan(row.relative_return_6m) or row.relative_return_6m > config.min_relative_return:
            reasons.add("relative_return_threshold_not_met")
        if math.isnan(row.oversold_score) or row.oversold_score < config.min_oversold_score:
            reasons.add("oversold_score_below_threshold")
        if math.isnan(row.base_upside) or row.base_upside < config.min_base_upside:
            reasons.add("base_upside_below_threshold")
        if not row.evidence_complete:
            reasons.add("evidence_incomplete")
        if row.hard_risk_triggered:
            reasons.add("hard_risk_triggered")
        if row.hard_risk_review_unknown:
            reasons.add("hard_risk_review_unknown")
        if not row.balance_sheet_coverage:
            reasons.add("balance_sheet_coverage_insufficient")
        if row.repair_bucket not in {EXPECTED_REPAIR, EARLY_VALIDATION}:
            reasons.add("repair_bucket_invalid")

        repair_values = (
            row.latest_revenue_growth,
            row.normal_revenue_growth,
            row.latest_profit_growth,
            row.normal_profit_growth,
            row.latest_net_margin,
            row.normal_net_margin,
        )
        repair_complete = explicitly_completed
        if not any(math.isnan(value) for value in repair_values):
            repair_complete = repair_complete or (
                row.normal_revenue_growth > 0.0
                and row.normal_profit_growth > 0.0
                and row.normal_net_margin > 0.0
                and _at_least_ninety_percent(
                    row.latest_revenue_growth, row.normal_revenue_growth
                )
                and _at_least_ninety_percent(
                    row.latest_profit_growth, row.normal_profit_growth
                )
                and _at_least_ninety_percent(row.latest_net_margin, row.normal_net_margin)
            )
        if repair_complete:
            reasons.add("repair_already_completed")
        if math.isnan(row.composite_score):
            reasons.add("composite_score_missing")

        ordered_reasons = sorted(reasons)
        eligible_values.append(not ordered_reasons)
        reason_values.append("|".join(ordered_reasons))

    frame["eligible"] = eligible_values
    frame["exclusion_reasons"] = reason_values
    return frame.sort_values("asset_id", kind="stable").reset_index(drop=True)


def rank_candidate_buckets(
    scored_rows: pd.DataFrame, config: ConsumerOversoldConfig
) -> dict[str, pd.DataFrame]:
    """Return independently capped, deterministic expected and early repair rankings."""
    scored_rows = _supply_empty_schema(scored_rows, RANK_REQUIRED_COLUMNS)
    _require_columns(scored_rows, RANK_REQUIRED_COLUMNS, "scored_rows")
    frame = _prepare_assets(scored_rows, "scored_rows")
    _assign_numeric(frame, ("composite_score", "base_upside"), "scored_rows")
    frame["eligible"] = [
        _parse_boolean(value, "eligible", asset_id)
        for value, asset_id in zip(frame["eligible"], frame["asset_id"], strict=True)
    ]
    for field in ("composite_score", "base_upside"):
        invalid = frame["eligible"] & frame[field].isna()
        if invalid.any():
            asset_id = frame.loc[invalid, "asset_id"].sort_values(kind="stable").iloc[0]
            raise ValueError(
                f"scored_rows asset {asset_id} field {field} must be present for eligible assets"
            )
    output: dict[str, pd.DataFrame] = {}
    for output_name, repair_bucket in (
        ("expected", EXPECTED_REPAIR),
        ("early", EARLY_VALIDATION),
    ):
        ranked = frame.loc[frame["eligible"] & frame["repair_bucket"].eq(repair_bucket)].copy()
        ranked = ranked.sort_values(
            ["composite_score", "base_upside", "asset_id"],
            ascending=[False, False, True],
            kind="stable",
            na_position="last",
        ).head(config.max_per_bucket)
        ranked["bucket_rank"] = np.arange(1, len(ranked) + 1, dtype=int)
        output[output_name] = ranked.reset_index(drop=True)
    return output
