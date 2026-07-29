from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS

from .contracts import ConsumerOversoldConfig
from .evidence import EVIDENCE_COLUMNS, validate_repair_evidence
from .features import (
    CURRENT_VALUATION_COLUMNS,
    VALUATION_HISTORY_COLUMNS,
    compute_already_priced_features,
    compute_fundamental_features,
    compute_hard_risk_features,
    compute_oversold_score,
    compute_price_features,
    compute_valuation_features,
)
from .loaders import (
    load_consumer_earnings_forecasts,
    load_consumer_finance_history,
    load_consumer_market_history,
    load_consumer_universe_frames,
    load_consumer_valuation_history,
)
from .reporting import _render_report, write_consumer_oversold_artifacts
from .scoring import apply_candidate_gates, rank_candidate_buckets, score_candidates
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

    included_ids = set(included["asset_id"])
    bars = copied["bars"].loc[copied["bars"]["asset_id"].astype(str).isin(included_ids)].copy()
    finance = copied["finance"].loc[copied["finance"]["asset_id"].astype(str).isin(included_ids)].copy()
    price = compute_price_features(bars, membership, trade_date=config.trade_date)
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

    current, valuation_history, valuation_fundamentals, warnings = _prepare_valuation_inputs(
        copied["current_valuation"],
        copied["valuation_history"],
        fundamentals,
        membership,
        config.trade_date,
    )
    valuation = compute_valuation_features(current, valuation_history, valuation_fundamentals)

    candidates = included.rename(columns={"name": "stock_name"})
    candidates = _merge_one_to_one(
        candidates,
        price.drop(columns=["consumer_subindustry"], errors="ignore"),
        "price_features",
    )
    candidates = _merge_one_to_one(candidates, fundamentals, "fundamental_features")
    candidates = _merge_one_to_one(candidates, risk, "hard_risk_features")
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
    ranked = rank_candidate_buckets(gated, config)

    universe_exclusions = universe.loc[~universe["included"].astype(bool)].rename(
        columns={
            "name": "stock_name",
            "exclude_reasons": "exclusion_reasons",
        }
    )
    universe_exclusions["exclusion_stage"] = "universe"
    universe_exclusions = universe_exclusions.reindex(columns=EXCLUSION_ID_COLUMNS)
    gate_exclusions = gated.loc[~gated["eligible"]].copy()
    gate_exclusions["exclusion_stage"] = "gate"
    gate_columns = [*EXCLUSION_ID_COLUMNS, *[column for column in gated.columns if column not in EXCLUSION_ID_COLUMNS]]
    gate_exclusions = gate_exclusions.reindex(columns=gate_columns)
    exclusions = pd.concat([universe_exclusions, gate_exclusions], ignore_index=True, sort=False)
    exclusions = exclusions.sort_values(
        ["exclusion_stage", "asset_id"], kind="stable"
    ).reset_index(drop=True)

    coverage = _coverage(
        raw_assets=copied["assets"],
        included=included,
        scores=gated,
        evidence=validated_evidence,
        bars=bars,
        finance=finance,
        valuation_history=valuation_history,
        expected=ranked["expected"],
        early=ranked["early"],
        config=config,
        warnings=warnings,
    )
    payload = {
        "trade_date": config.trade_date,
        "expected": ranked["expected"],
        "early": ranked["early"],
        "scores": gated,
        "exclusions": exclusions,
        "coverage": coverage,
    }
    if output_dir is not None:
        return write_consumer_oversold_artifacts(payload, output_dir=output_dir)
    return {
        "paths": {},
        "expected": ranked["expected"],
        "early": ranked["early"],
        "scores": gated,
        "exclusions": exclusions,
        "coverage": coverage,
        "report": _render_report(
            config.trade_date,
            ranked["expected"],
            ranked["early"],
            exclusions,
            coverage,
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
        market_cap = pe * profit if math.isfinite(pe) and math.isfinite(profit) else math.nan
        if not math.isfinite(market_cap) and math.isfinite(ps) and math.isfinite(revenue):
            market_cap = ps * revenue
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
    bars = load_consumer_market_history(trade_date, service=service)
    finance = load_consumer_finance_history(asset_ids, trade_date, service=service)
    valuation_raw = load_consumer_valuation_history(asset_ids, trade_date, service=service)
    earnings = load_consumer_earnings_forecasts(asset_ids, trade_date, service=service)
    fundamentals = compute_fundamental_features(finance, trade_date=trade_date)
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
        valuation_history, fundamentals, included, trade_date
    )
    frames = {
        **universe_frames,
        "industry_rules": industry_rules,
        "asset_overrides": asset_overrides,
        "bars": bars,
        "finance": finance,
        "current_valuation": current_valuation,
        "valuation_history": valuation_history,
        "earnings": earnings,
    }
    return build_consumer_oversold_weekly_from_frames(
        frames=frames,
        evidence=evidence,
        config=config,
        output_dir=output_dir,
    )
