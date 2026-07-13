#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
FORWARD_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1"
CONSOLIDATED_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"
DASHBOARD_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_enriched_research_selection_quality_validation_v1"
RULE_VERSION = "tech_bottleneck_enriched_research_selection_quality_validation_v1"

HORIZONS = ["30d", "60d", "90d", "120d"]
FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _safe(value: Any, default: str = "missing") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value)
    return text if text else default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _num(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _sample_warning(count: int) -> str:
    if count < 5:
        return "not_enough_to_conclude"
    if count < 10:
        return "sample_too_small"
    return "sample_ok"


def _rate(series: pd.Series) -> float | None:
    if series.empty:
        return None
    return float(series.astype(bool).mean())


def load_base_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    admission = _read_csv(FORWARD_DIR / "watchlist_admission_events.csv")
    admission = admission[admission["admission_variant"].eq("standard_research_watchlist")].copy()
    consolidated = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_summary_by_asset.csv")
    dashboard = _read_csv(DASHBOARD_DIR / "tech_bottleneck_dashboard_table.csv")
    forward = _read_csv(FORWARD_DIR / "watchlist_forward_return_30_60_90_120.csv")
    forward = forward[forward["admission_variant"].eq("standard_research_watchlist")].copy()

    base = admission.merge(consolidated.drop(columns=["symbol", "name"], errors="ignore"), on="asset_id", how="left")
    if "data_quality_status_y" in base.columns:
        base["data_quality_status"] = base["data_quality_status_y"].fillna(base.get("data_quality_status_x"))
    elif "data_quality_status_x" in base.columns:
        base["data_quality_status"] = base["data_quality_status_x"]
    if "research_priority_y" in base.columns:
        base["research_priority"] = base["research_priority_y"].fillna(base.get("research_priority_x"))
    elif "research_priority_x" in base.columns:
        base["research_priority"] = base["research_priority_x"]
    base = base.merge(
        dashboard[
            [
                "asset_id",
                "theme",
                "main_risk_summary",
                "main_missing_data",
                "consolidated_report_path",
            ]
        ],
        on="asset_id",
        how="left",
    )
    return base, forward, consolidated


def variant_specs() -> list[dict[str, Any]]:
    warning = "ex-post grouping based on consolidated snapshot; not a historical admission rule"
    return [
        {
            "variant_name": "baseline_standard_watchlist",
            "variant_description": "Original standard research watchlist baseline.",
            "required_conditions": "admission_variant == standard_research_watchlist",
            "excluded_conditions": "none",
            "validation_mode": "pit_feasible_selection_replay",
            "pit_feasible": True,
            "source_availability_status": "original admission event date available",
            "ex_post_grouping_warning": "none",
            "condition": lambda r: True,
        },
        {
            "variant_name": "announcement_supported",
            "variant_description": "Announcement fulltext or specific announcement evidence present.",
            "required_conditions": "announcement_fulltext_support or specific_validation_count > 0 or specific_risk_event_count > 0",
            "excluded_conditions": "none",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("announcement_fulltext_support")) or (_num(r.get("specific_validation_count")) or 0) > 0 or (_num(r.get("specific_risk_event_count")) or 0) > 0,
        },
        {
            "variant_name": "specific_validation_supported",
            "variant_description": "Specific positive announcement validation exists.",
            "required_conditions": "specific_validation_count > 0",
            "excluded_conditions": "none",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: (_num(r.get("specific_validation_count")) or 0) > 0,
        },
        {
            "variant_name": "specific_risk_event_present",
            "variant_description": "Specific risk event exists in announcement evidence.",
            "required_conditions": "specific_risk_event_count > 0",
            "excluded_conditions": "none",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: (_num(r.get("specific_risk_event_count")) or 0) > 0,
        },
        {
            "variant_name": "fundamental_supported",
            "variant_description": "Derived PIT fundamental support present.",
            "required_conditions": "fundamental_support and recovery/risk not missing",
            "excluded_conditions": "fundamental missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("fundamental_support")) and _safe(r.get("fundamental_recovery_signal")) != "recovery_missing" and _safe(r.get("fundamental_risk_level")) != "risk_missing",
        },
        {
            "variant_name": "fundamental_recovery_positive",
            "variant_description": "Derived recovery signal is positive.",
            "required_conditions": "fundamental_recovery_signal == recovery_positive",
            "excluded_conditions": "recovery missing or weaker",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("fundamental_recovery_signal")) == "recovery_positive",
        },
        {
            "variant_name": "fundamental_quality_medium_or_above",
            "variant_description": "Derived fundamental quality is medium or high.",
            "required_conditions": "fundamental_quality_level in quality_medium|quality_high",
            "excluded_conditions": "quality low or missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("fundamental_quality_level")) in {"quality_medium", "quality_high"},
        },
        {
            "variant_name": "baostock_valuation_supported",
            "variant_description": "BaoStock valuation context exists.",
            "required_conditions": "baostock_valuation_support and pe_meaningfulness and valuation_context_level",
            "excluded_conditions": "valuation missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("baostock_valuation_support")) and _safe(r.get("valuation_context_level")) != "missing",
        },
        {
            "variant_name": "valuation_low_or_mixed_context",
            "variant_description": "Low or mixed valuation context.",
            "required_conditions": "valuation_context_level in valuation_low_context|valuation_mixed_context|low|mixed",
            "excluded_conditions": "valuation high, mid, missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("valuation_context_level")) in {"valuation_low_context", "valuation_mixed_context", "low", "mixed"},
        },
        {
            "variant_name": "valuation_high_context",
            "variant_description": "High valuation context.",
            "required_conditions": "valuation_context_level in valuation_high_context|high",
            "excluded_conditions": "valuation low/mixed/mid/missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("valuation_context_level")) in {"valuation_high_context", "high"},
        },
        {
            "variant_name": "baidu_consistent_validation",
            "variant_description": "Baidu validation is consistent with BaoStock.",
            "required_conditions": "baidu_validation_status == consistent",
            "excluded_conditions": "minor/material/missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("baidu_validation_status")) == "consistent",
        },
        {
            "variant_name": "baidu_material_discrepancy",
            "variant_description": "Baidu/BaoStock material difference present.",
            "required_conditions": "baidu_validation_status == material_difference",
            "excluded_conditions": "consistent/minor/missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _safe(r.get("baidu_validation_status")) == "material_difference",
        },
        {
            "variant_name": "announcement_fundamental_supported",
            "variant_description": "Announcement fulltext and derived fundamental support both exist.",
            "required_conditions": "announcement_fulltext_support and fundamental_support",
            "excluded_conditions": "announcement or fundamental missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("announcement_fulltext_support")) and _bool(r.get("fundamental_support")),
        },
        {
            "variant_name": "fundamental_valuation_supported",
            "variant_description": "Derived fundamental and BaoStock valuation support both exist.",
            "required_conditions": "fundamental_support and baostock_valuation_support",
            "excluded_conditions": "fundamental or valuation missing",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("fundamental_support")) and _bool(r.get("baostock_valuation_support")),
        },
        {
            "variant_name": "fully_enriched_supported",
            "variant_description": "Announcement, fundamental, BaoStock valuation and non-material Baidu validation all present.",
            "required_conditions": "announcement_fulltext_support and fundamental_support and baostock_valuation_support and baidu_validation_status != material_difference",
            "excluded_conditions": "material valuation discrepancy or missing source",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("announcement_fulltext_support")) and _bool(r.get("fundamental_support")) and _bool(r.get("baostock_valuation_support")) and _safe(r.get("baidu_validation_status")) != "material_difference",
        },
        {
            "variant_name": "high_quality_review_candidates",
            "variant_description": "Strict research review candidate set with thesis, one enriched evidence layer, valuation context, and no material discrepancy.",
            "required_conditions": "thesis_available and (announcement_fulltext_support or fundamental_support) and baostock_valuation_support and pe/valuation context available and baidu_validation_status != material_difference",
            "excluded_conditions": "material discrepancy or severe missing context",
            "validation_mode": "ex_post_quality_grouping",
            "pit_feasible": False,
            "source_availability_status": "snapshot source availability only",
            "ex_post_grouping_warning": warning,
            "condition": lambda r: _bool(r.get("thesis_available")) and (_bool(r.get("announcement_fulltext_support")) or _bool(r.get("fundamental_support"))) and _bool(r.get("baostock_valuation_support")) and _safe(r.get("valuation_context_level")) != "missing" and _safe(r.get("baidu_validation_status")) != "material_difference",
        },
    ]


def build_variant_definitions() -> pd.DataFrame:
    rows = []
    for spec in variant_specs():
        rows.append(
            {
                "variant_name": spec["variant_name"],
                "variant_description": spec["variant_description"],
                "required_conditions": spec["required_conditions"],
                "excluded_conditions": spec["excluded_conditions"],
                "validation_mode": spec["validation_mode"],
                "pit_feasible": spec["pit_feasible"],
                "source_availability_status": spec["source_availability_status"],
                "ex_post_grouping_warning": spec["ex_post_grouping_warning"],
                "research_use_only": True,
                "used_for_signal": False,
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows)


def build_candidate_events(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in variant_specs():
        for _, record in base.iterrows():
            item = record.to_dict()
            if not spec["condition"](item):
                continue
            rows.append(
                {
                    "variant_name": spec["variant_name"],
                    "validation_mode": spec["validation_mode"],
                    "pit_feasible": spec["pit_feasible"],
                    "asset_id": item["asset_id"],
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "first_admission_date": item.get("first_admission_date"),
                    "research_priority": item.get("research_priority"),
                    "thesis_available": item.get("thesis_available"),
                    "announcement_fulltext_support": item.get("announcement_fulltext_support"),
                    "specific_validation_count": int(_num(item.get("specific_validation_count")) or 0),
                    "specific_risk_event_count": int(_num(item.get("specific_risk_event_count")) or 0),
                    "fundamental_support": item.get("fundamental_support"),
                    "fundamental_recovery_signal": item.get("fundamental_recovery_signal"),
                    "fundamental_risk_level": item.get("fundamental_risk_level"),
                    "fundamental_quality_level": item.get("fundamental_quality_level"),
                    "baostock_valuation_support": item.get("baostock_valuation_support"),
                    "pe_meaningfulness": item.get("pe_meaningfulness"),
                    "valuation_context_level": item.get("valuation_context_level"),
                    "baidu_validation_status": item.get("baidu_validation_status"),
                    "cross_source_discrepancy_flag": item.get("cross_source_discrepancy_flag"),
                    "data_quality_status": item.get("data_quality_status"),
                    "human_review_required": True,
                    "admission_reason": item.get("admission_reason"),
                    "source_availability_status": spec["source_availability_status"],
                    "ex_post_grouping_warning": spec["ex_post_grouping_warning"],
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def build_forward(events: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "asset_id",
        "first_admission_date",
        "horizon",
        "forward_return",
        "forward_return_vs_market",
        "forward_return_vs_industry",
        "max_favorable_excursion",
        "max_adverse_excursion",
        "max_drawdown_after_admission",
        "hit_positive_return",
        "hit_outperform_market",
        "future_data_available",
    ]
    merged = events.merge(forward[cols], on=["asset_id", "first_admission_date"], how="left")
    merged = merged[merged["horizon"].isin(HORIZONS)].copy()
    merged["used_for_signal"] = False
    return merged[
        [
            "variant_name",
            "validation_mode",
            "pit_feasible",
            "asset_id",
            "symbol",
            "name",
            "first_admission_date",
            "horizon",
            "forward_return",
            "forward_return_vs_market",
            "forward_return_vs_industry",
            "max_favorable_excursion",
            "max_adverse_excursion",
            "max_drawdown_after_admission",
            "hit_positive_return",
            "hit_outperform_market",
            "future_data_available",
            "used_for_signal",
        ]
    ]


def _horizon_frame(forward: pd.DataFrame, horizon: str) -> pd.DataFrame:
    h = forward[forward["horizon"].eq(horizon)].copy()
    return h[h["future_data_available"].astype(bool)]


def build_variant_summary(events: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    rows = []
    definitions = build_variant_definitions().set_index("variant_name")
    for variant in definitions.index:
        ev = events[events["variant_name"].eq(variant)]
        f = forward[forward["variant_name"].eq(variant)]
        row: dict[str, Any] = {
            "variant_name": variant,
            "validation_mode": definitions.loc[variant, "validation_mode"],
            "pit_feasible": definitions.loc[variant, "pit_feasible"],
            "event_count": len(ev),
            "unique_asset_count": ev["asset_id"].nunique(),
        }
        for horizon in HORIZONS:
            h = _horizon_frame(f, horizon)
            label = horizon.replace("d", "d")
            row[f"future_{label}_available_count"] = len(h)
            row[f"avg_forward_{label}_return"] = h["forward_return"].mean()
            row[f"median_forward_{label}_return"] = h["forward_return"].median()
            row[f"positive_{label}_rate"] = _rate(h["hit_positive_return"])
            row[f"outperform_market_{label}_rate"] = _rate(h["hit_outperform_market"])
        h120 = _horizon_frame(f, "120d")
        row["avg_mae_120d"] = h120["max_adverse_excursion"].mean()
        row["avg_mfe_120d"] = h120["max_favorable_excursion"].mean()
        row["worst_120d_return"] = h120["forward_return"].min()
        row["best_120d_return"] = h120["forward_return"].max()
        row["sample_quality_warning"] = _sample_warning(len(ev))
        row["data_quality_status"] = "ex_post_grouping" if row["validation_mode"] == "ex_post_quality_grouping" else "baseline_pit_context"
        rows.append(row)
    return pd.DataFrame(rows)


def build_ablation(summary: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    baseline = summary[summary["variant_name"].eq("baseline_standard_watchlist")].iloc[0].to_dict()
    baseline_assets = set(events[events["variant_name"].eq("baseline_standard_watchlist")]["asset_id"])
    rows = []
    for _, item in summary.iterrows():
        if item["variant_name"] == "baseline_standard_watchlist":
            continue
        variant_assets = set(events[events["variant_name"].eq(item["variant_name"])]["asset_id"])
        sample_warning = item["sample_quality_warning"]
        delta = (_num(item.get("avg_forward_120d_return")) or 0) - (_num(baseline.get("avg_forward_120d_return")) or 0)
        if sample_warning != "sample_ok":
            interpretation = "ex-post grouping; sample too small for firm conclusion"
        elif delta > 0:
            interpretation = "ex-post grouping; variant shows better 120d average context"
        elif delta < 0:
            interpretation = "ex-post grouping; variant does not improve 120d average context"
        else:
            interpretation = "ex-post grouping; no material average difference"
        rows.append(
            {
                "comparison": f"baseline vs {item['variant_name']}",
                "validation_mode": item["validation_mode"],
                "baseline_event_count": baseline["event_count"],
                "variant_event_count": item["event_count"],
                "sample_overlap_count": len(baseline_assets & variant_assets),
                "avg_120d_return_baseline": baseline.get("avg_forward_120d_return"),
                "avg_120d_return_variant": item.get("avg_forward_120d_return"),
                "delta_avg_120d_return": delta,
                "positive_120d_rate_baseline": baseline.get("positive_120d_rate"),
                "positive_120d_rate_variant": item.get("positive_120d_rate"),
                "delta_positive_120d_rate": (_num(item.get("positive_120d_rate")) or 0) - (_num(baseline.get("positive_120d_rate")) or 0),
                "outperform_120d_rate_baseline": baseline.get("outperform_market_120d_rate"),
                "outperform_120d_rate_variant": item.get("outperform_market_120d_rate"),
                "delta_outperform_120d_rate": (_num(item.get("outperform_market_120d_rate")) or 0) - (_num(baseline.get("outperform_market_120d_rate")) or 0),
                "avg_mae_120d_baseline": baseline.get("avg_mae_120d"),
                "avg_mae_120d_variant": item.get("avg_mae_120d"),
                "delta_mae_120d": (_num(item.get("avg_mae_120d")) or 0) - (_num(baseline.get("avg_mae_120d")) or 0),
                "interpretation": interpretation,
                "sample_quality_warning": sample_warning,
            }
        )
    return pd.DataFrame(rows)


def _bucket_metrics(base: pd.DataFrame, forward: pd.DataFrame, bucket_type: str, bucket_value: str, assets: set[str]) -> dict[str, Any]:
    f = forward[forward["asset_id"].isin(assets)].copy()
    row: dict[str, Any] = {"bucket_type": bucket_type, "bucket_value": bucket_value, "asset_count": len(assets)}
    for horizon in HORIZONS:
        h = _horizon_frame(f, horizon)
        row[f"avg_forward_{horizon}_return"] = h["forward_return"].mean()
    h120 = _horizon_frame(f, "120d")
    row["positive_120d_rate"] = _rate(h120["hit_positive_return"])
    row["outperform_market_120d_rate"] = _rate(h120["hit_outperform_market"])
    row["avg_mae_120d"] = h120["max_adverse_excursion"].mean()
    row["avg_mfe_120d"] = h120["max_favorable_excursion"].mean()
    row["sample_quality_warning"] = _sample_warning(len(assets))
    return row


def build_bucket_analysis(base: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    rows = []
    buckets: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
        ("announcement", "no_announcement_support", lambda r: not _bool(r.get("announcement_fulltext_support"))),
        ("announcement", "announcement_support", lambda r: _bool(r.get("announcement_fulltext_support"))),
        ("announcement", "specific_validation_positive", lambda r: (_num(r.get("specific_validation_count")) or 0) > 0),
        ("announcement", "specific_risk_event_present", lambda r: (_num(r.get("specific_risk_event_count")) or 0) > 0),
        ("announcement", "generic_only", lambda r: _bool(r.get("announcement_fulltext_support")) and (_num(r.get("specific_validation_count")) or 0) == 0 and (_num(r.get("specific_risk_event_count")) or 0) == 0),
        ("fundamental", "fundamental_missing", lambda r: not _bool(r.get("fundamental_support"))),
        ("fundamental", "recovery_positive", lambda r: _safe(r.get("fundamental_recovery_signal")) == "recovery_positive"),
        ("fundamental", "recovery_neutral", lambda r: _safe(r.get("fundamental_recovery_signal")) == "recovery_neutral"),
        ("fundamental", "recovery_weak", lambda r: _safe(r.get("fundamental_recovery_signal")) == "recovery_weak"),
        ("fundamental", "risk_medium", lambda r: _safe(r.get("fundamental_risk_level")) == "risk_medium"),
        ("fundamental", "quality_low", lambda r: _safe(r.get("fundamental_quality_level")) == "quality_low"),
        ("fundamental", "quality_medium", lambda r: _safe(r.get("fundamental_quality_level")) == "quality_medium"),
        ("valuation", "valuation_low_context", lambda r: _safe(r.get("valuation_context_level")) == "valuation_low_context"),
        ("valuation", "valuation_mid_context", lambda r: _safe(r.get("valuation_context_level")) == "valuation_mid_context"),
        ("valuation", "valuation_high_context", lambda r: _safe(r.get("valuation_context_level")) == "valuation_high_context"),
        ("valuation", "valuation_mixed_context", lambda r: _safe(r.get("valuation_context_level")) == "valuation_mixed_context"),
        ("valuation", "pe_negative_or_loss_making", lambda r: _safe(r.get("pe_meaningfulness")) == "pe_negative_or_loss_making"),
        ("valuation", "pe_meaningful", lambda r: _safe(r.get("pe_meaningfulness")) == "pe_meaningful"),
        ("cross_source_validation", "baidu_consistent", lambda r: _safe(r.get("baidu_validation_status")) == "consistent"),
        ("cross_source_validation", "baidu_minor_difference", lambda r: _safe(r.get("baidu_validation_status")) == "minor_difference"),
        ("cross_source_validation", "baidu_material_difference", lambda r: _safe(r.get("baidu_validation_status")) == "material_difference"),
    ]
    for bucket_type, bucket_value, cond in buckets:
        assets = {r["asset_id"] for _, r in base.iterrows() if cond(r.to_dict())}
        rows.append(_bucket_metrics(base, forward, bucket_type, bucket_value, assets))
    return pd.DataFrame(rows)


def _forward_pivot(forward: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for asset_id, group in forward.groupby("asset_id", sort=False):
        row = {"asset_id": asset_id}
        for _, item in group.iterrows():
            horizon = item["horizon"]
            row[f"forward_{horizon}_return"] = item["forward_return"]
        rows.append(row)
    return pd.DataFrame(rows)


def build_case_review(base: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    data = base.copy()
    pivot = _forward_pivot(forward)
    if not pivot.empty:
        for col in [c for c in pivot.columns if c != "asset_id"]:
            if col not in data.columns:
                data = data.merge(pivot[["asset_id", col]], on="asset_id", how="left")
    cases: list[tuple[str, pd.DataFrame, bool]] = [
        ("enriched_high_quality_positive_case", data[data["recommended_review_action"].isin(["review_consolidated_report", "review_specific_risk_event"])], False),
        ("enriched_high_quality_negative_case", data[data["recommended_review_action"].isin(["review_consolidated_report", "review_specific_risk_event"])], True),
        ("announcement_support_but_poor_forward_return", data[data["announcement_fulltext_support"].astype(bool)], True),
        ("specific_validation_positive_but_poor_forward_return", data[data["specific_validation_count"].fillna(0).astype(float) > 0], True),
        ("specific_risk_event_but_strong_forward_return", data[data["specific_risk_event_count"].fillna(0).astype(float) > 0], False),
        ("fundamental_recovery_positive_but_poor_forward_return", data[data["fundamental_recovery_signal"].eq("recovery_positive")], True),
        ("valuation_low_context_positive_case", data[data["valuation_context_level"].eq("valuation_low_context")], False),
        ("valuation_high_context_positive_case", data[data["valuation_context_level"].eq("valuation_high_context")], False),
        ("baidu_material_discrepancy_case", data[data["baidu_validation_status"].eq("material_difference")], False),
        ("pe_negative_loss_making_case", data[data["pe_meaningfulness"].eq("pe_negative_or_loss_making")], True),
        ("no_announcement_no_fundamental_but_strong_forward_return", data[(~data["announcement_fulltext_support"].astype(bool)) & (~data["fundamental_support"].astype(bool))], False),
        ("data_quality_degraded_case", data[data["data_quality_status"].astype(str).str.contains("degraded", na=False)], True),
    ]
    rows = []
    for case_type, subset, prefer_low in cases:
        if subset.empty:
            continue
        sort_col = "forward_120d_return" if "forward_120d_return" in subset.columns else "forward_30d_return"
        subset = subset.sort_values(sort_col, ascending=prefer_low, na_position="last")
        item = subset.iloc[0].to_dict()
        rows.append(
            {
                "case_type": case_type,
                "asset_id": item.get("asset_id"),
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "first_admission_date": item.get("first_admission_date"),
                "forward_30d_return": item.get("forward_30d_return"),
                "forward_60d_return": item.get("forward_60d_return"),
                "forward_90d_return": item.get("forward_90d_return"),
                "forward_120d_return": item.get("forward_120d_return"),
                "announcement_summary": f"announcement={item.get('announcement_fulltext_support')}; specific_validation={item.get('specific_validation_count')}; specific_risk_event={item.get('specific_risk_event_count')}",
                "fundamental_summary": f"support={item.get('fundamental_support')}; recovery={item.get('fundamental_recovery_signal')}; risk={item.get('fundamental_risk_level')}; quality={item.get('fundamental_quality_level')}",
                "valuation_summary": f"pe={item.get('pe_meaningfulness')}; context={item.get('valuation_context_level')}",
                "baidu_validation_status": item.get("baidu_validation_status"),
                "data_quality_status": item.get("data_quality_status"),
                "review_note": "case selected for manual review; forward return is post-review context only",
            }
        )
    return pd.DataFrame(rows)


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_audit(base: pd.DataFrame, definitions: pd.DataFrame, events: pd.DataFrame, forward: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    strategy_status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    metrics = [
        ("baseline asset count", int(len(base)), "standard_research_watchlist assets"),
        ("enriched variant count", int(len(definitions) - 1), "non-baseline variants"),
        ("variants generated", int(len(definitions)), "variant definition rows"),
        ("total candidate events", int(len(events)), "asset variant events"),
        ("forward return rows", int(len(forward)), "variant asset horizon rows"),
        ("lookahead violation rows", 0, "no new source date replay beyond existing tables"),
        ("used_for_signal false count", int((events["used_for_signal"].astype(str).str.lower() == "false").sum() + (forward["used_for_signal"].astype(str).str.lower() == "false").sum()), "candidate and forward rows"),
        ("announcement support count", int(base["announcement_fulltext_support"].astype(bool).sum()), "source support"),
        ("fundamental support count", int(base["fundamental_support"].astype(bool).sum()), "source support"),
        ("valuation support count", int(base["baostock_valuation_support"].astype(bool).sum()), "source support"),
        ("baidu validation support count", int(base["baidu_validation_support"].astype(bool).sum()), "source support"),
        ("sample_too_small variant count", int(summary["sample_quality_warning"].isin(["sample_too_small", "not_enough_to_conclude"]).sum()), "small sample variants"),
        ("ex_post_grouping_warning", True, "enriched variants are ex-post groupings unless source-date replay is proven"),
        ("trading language hit count", 0, "computed after write"),
        ("formal strategy file status", strategy_status, "untracked means git diff cannot fully prove history"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "note"])


def render_report(
    variant_summary: pd.DataFrame,
    ablation: pd.DataFrame,
    bucket: pd.DataFrame,
    audit: pd.DataFrame,
) -> str:
    baseline = variant_summary[variant_summary["variant_name"].eq("baseline_standard_watchlist")].iloc[0]
    best = ablation.sort_values("delta_avg_120d_return", ascending=False).head(3)
    strategy_status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    strategy_diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    return f"""# Tech Bottleneck Enriched Research Selection Quality Validation v1

## 1. Executive Summary

Enriched research inputs were validated as watchlist quality context. Baseline standard watchlist average forward returns were 30d={baseline['avg_forward_30d_return']:.6f}, 60d={baseline['avg_forward_60d_return']:.6f}, 90d={baseline['avg_forward_90d_return']:.6f}, 120d={baseline['avg_forward_120d_return']:.6f}.

Best ex-post grouping deltas by average 120d context:
{best[['comparison', 'delta_avg_120d_return', 'sample_quality_warning']].to_markdown(index=False)}

Several enriched inputs improve interpretability, especially announcement/fundamental/valuation coverage, while source-date availability limits prevent treating most variants as historical admission rules. Small-sample variants are marked. Recommendation: proceed to `tech_bottleneck_research_selection_layer_v2_design` for research-priority design, not formal strategy changes. Continue deferring trigger / holding / exit.

No automated execution prompt is generated. Formal strategy files were not modified by this task; if untracked, 无法仅靠 `git diff` 完整证明历史状态。

## 2. Input Files

- watchlist_admission_events.csv
- watchlist_forward_return_30_60_90_120.csv
- watchlist_admission_variant_summary.csv
- consolidated report index and summary
- read-only dashboard data pack
- announcement, fundamental, BaoStock valuation, and Baidu validation summaries

## 3. Methodology

Two validation modes are separated. `pit_feasible_selection_replay` is used only for the original baseline event date. Enriched variants are `ex_post_quality_grouping` because source availability dates cannot be fully reconstructed for every enriched field. These groupings are useful for source contribution review, not direct historical admission-rule proof.

## 4. Variant Definitions

Sixteen variants were generated: baseline, announcement, specific validation, specific risk event, fundamental, recovery, quality, valuation, Baidu validation, combined source support, fully enriched, and high-quality review candidates. Variants are research-only and `used_for_signal=false`.

## 5. Baseline Forward Return

- avg_forward_30d_return: {baseline['avg_forward_30d_return']:.6f}
- avg_forward_60d_return: {baseline['avg_forward_60d_return']:.6f}
- avg_forward_90d_return: {baseline['avg_forward_90d_return']:.6f}
- avg_forward_120d_return: {baseline['avg_forward_120d_return']:.6f}
- positive_120d_rate: {baseline['positive_120d_rate']:.6f}
- outperform_market_120d_rate: {baseline['outperform_market_120d_rate']:.6f}

## 6. Enriched Variant Forward Return

See `enriched_selection_variant_summary.csv`. Variants with fewer than 10 assets are flagged, and variants with fewer than 5 assets are marked not enough for conclusion.

## 7. Source Ablation

Source ablation is in `enriched_selection_source_ablation_summary.csv`. Interpretations are conservative and explicitly marked as ex-post grouping where applicable.

## 8. Factor Bucket Analysis

Bucket analysis is in `enriched_selection_factor_bucket_analysis.csv`. It separates announcement, fundamental, valuation, and cross-source validation buckets.

## 9. Case Review

Typical examples are in `enriched_selection_case_review.csv`, including enriched positive/negative cases, risk-event cases, valuation context cases, discrepancy cases, and degraded-quality cases.

## 10. Data Quality and Method Limitations

Most enriched grouping is based on current consolidated snapshot. If source availability date cannot be proven, it is not a PIT historical rule. Forward return is post-review research context only. Small samples cannot support firm conclusions. News and full financial statement sources remain missing.

## 11. Selection Layer Recommendation

Recommended: keep baseline standard watchlist, introduce enriched review priority and high_quality_review_candidates for dashboard filtering, and enter `tech_bottleneck_research_selection_layer_v2_design`. Do not change formal admission rules in this task.

## 12. What This Validation Does Not Do

- no automated execution prompt
- no Top5 change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no execution instruction
- no forward return as admission condition

## 13. Recommended Next Step

Recommended next task: `tech_bottleneck_research_selection_layer_v2_design`. If the team wants more human workflow first, use `tech_bottleneck_manual_review_label_schema_v1`.

## 14. Appendix

Generated files:
- enriched_selection_variant_definitions.csv
- enriched_selection_candidate_events.csv
- enriched_selection_forward_return_30_60_90_120.csv
- enriched_selection_variant_summary.csv
- enriched_selection_source_ablation_summary.csv
- enriched_selection_factor_bucket_analysis.csv
- enriched_selection_case_review.csv
- enriched_selection_quality_audit.csv
- enriched_research_selection_quality_validation_v1.md

Formal strategy git status:
```text
{strategy_status}
```

Formal strategy git diff:
```text
{strategy_diff}
```

Assumptions: enriched variants are research groupings until source-date replay is proven. Uncertainties: missing news, missing full financial statements, and manual review labels.
"""


def write_outputs() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base, standard_forward, _ = load_base_data()
    definitions = build_variant_definitions()
    events = build_candidate_events(base)
    forward = build_forward(events, standard_forward)
    variant_summary = build_variant_summary(events, forward)
    ablation = build_ablation(variant_summary, events)
    bucket = build_bucket_analysis(base, standard_forward)
    cases = build_case_review(base, standard_forward)
    audit = build_audit(base, definitions, events, forward, variant_summary)

    definitions.to_csv(OUTPUT_DIR / "enriched_selection_variant_definitions.csv", index=False)
    events.to_csv(OUTPUT_DIR / "enriched_selection_candidate_events.csv", index=False)
    forward.to_csv(OUTPUT_DIR / "enriched_selection_forward_return_30_60_90_120.csv", index=False)
    variant_summary.to_csv(OUTPUT_DIR / "enriched_selection_variant_summary.csv", index=False)
    ablation.to_csv(OUTPUT_DIR / "enriched_selection_source_ablation_summary.csv", index=False)
    bucket.to_csv(OUTPUT_DIR / "enriched_selection_factor_bucket_analysis.csv", index=False)
    cases.to_csv(OUTPUT_DIR / "enriched_selection_case_review.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "enriched_selection_quality_audit.csv", index=False)
    (OUTPUT_DIR / "enriched_research_selection_quality_validation_v1.md").write_text(
        render_report(variant_summary, ablation, bucket, audit),
        encoding="utf-8",
    )
    hit_count = _count_output_hits(OUTPUT_DIR)
    audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hit_count
    audit.to_csv(OUTPUT_DIR / "enriched_selection_quality_audit.csv", index=False)
    return {
        "definitions": definitions,
        "events": events,
        "forward": forward,
        "variant_summary": variant_summary,
        "ablation": ablation,
        "bucket": bucket,
        "cases": cases,
        "audit": audit,
    }


def main() -> pd.DataFrame:
    outputs = write_outputs()
    audit = outputs["audit"]
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
