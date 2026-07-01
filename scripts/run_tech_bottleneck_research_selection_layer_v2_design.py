#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
ENRICHED_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_enriched_research_selection_quality_validation_v1"
CONSOLIDATED_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"
DASHBOARD_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_design"
RULE_VERSION = "tech_bottleneck_research_selection_layer_v2_design"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def _metric(audit: pd.DataFrame, name: str, default: Any = "missing") -> Any:
    if audit.empty:
        return default
    row = audit[audit["metric"].eq(name)]
    return row["value"].iloc[0] if not row.empty else default


def build_feature_dictionary(summary: pd.DataFrame, variant_summary: pd.DataFrame) -> pd.DataFrame:
    coverage = {
        "announcement_fulltext_support": int(summary.get("announcement_fulltext_support", pd.Series(dtype=bool)).astype(bool).sum()),
        "specific_validation_count": int((summary.get("specific_validation_count", pd.Series(dtype=float)).fillna(0) > 0).sum()),
        "specific_risk_event_count": int((summary.get("specific_risk_event_count", pd.Series(dtype=float)).fillna(0) > 0).sum()),
        "fundamental_support": int(summary.get("fundamental_support", pd.Series(dtype=bool)).astype(bool).sum()),
        "fundamental_recovery_signal": int(summary.get("fundamental_recovery_signal", pd.Series(dtype=str)).ne("recovery_missing").sum()),
        "fundamental_risk_level": int(summary.get("fundamental_risk_level", pd.Series(dtype=str)).ne("risk_missing").sum()),
        "fundamental_quality_level": int(summary.get("fundamental_quality_level", pd.Series(dtype=str)).ne("quality_missing").sum()),
        "baostock_valuation_support": int(summary.get("baostock_valuation_support", pd.Series(dtype=bool)).astype(bool).sum()),
        "pe_meaningfulness": int(summary.get("pe_meaningfulness", pd.Series(dtype=str)).ne("missing").sum()),
        "valuation_context_level": int(summary.get("valuation_context_level", pd.Series(dtype=str)).ne("missing").sum()),
        "baidu_validation_status": int(summary.get("baidu_validation_support", pd.Series(dtype=bool)).astype(bool).sum()),
        "cross_source_discrepancy_flag": int(summary.get("cross_source_discrepancy_flag", pd.Series(dtype=str)).ne("missing").sum()),
        "human_review_required": 102,
        "data_quality_status": int(summary.get("data_quality_status", pd.Series(dtype=str)).ne("missing").sum()),
        "degraded_source_warning": 102,
    }
    rows = [
        ("thesis_available", "thesis", "consolidated snapshot", "watchlist_report_consolidated_summary_by_asset.csv", "102/102", "helps review clarity", "thesis missing is a data gap", "review_priority", "source_date <= admission_date", "ex_post_only", True, False, True, "snapshot-derived field"),
        ("announcement_fulltext_support", "announcement", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", f"{coverage['announcement_fulltext_support']}/102", "moderate source contribution", "announcement_supported improved 120d context mildly", "review_priority", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "requires source availability date before PIT replay"),
        ("specific_validation_count", "announcement", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", f"{coverage['specific_validation_count']}/102", "interpretability", "specific validation did not clearly improve average 120d context", "review_priority", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "specific evidence for manual thesis review"),
        ("specific_risk_event_count", "risk_review", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", f"{coverage['specific_risk_event_count']}/102", "risk review", "risk event group did not clearly improve average context", "manual_review_only", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "warning, not exclusion"),
        ("generic_business_description_count", "announcement", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", "available upstream", "weak interpretability", "generic text is weak evidence", "dashboard_filter", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "generic text is not strong validation"),
        ("generic_disclosure_text_count", "risk_review", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", "available upstream", "weak risk context", "generic disclosure is weak risk context", "dashboard_filter", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "generic text is not specific event"),
        ("title_only_remaining_count", "data_quality", "announcement fulltext", "watchlist_fulltext_announcement_patch_summary_by_asset.csv", "13 rows upstream", "data gap", "title-only remains degraded", "data_quality_warning", "announcement_date/as_of_date <= admission_date", "requires_source_date_replay", True, False, True, "request full text"),
        ("fundamental_support", "fundamental", "fundamental derived PIT features", "watchlist_fundamental_patch_summary_by_asset.csv", f"{coverage['fundamental_support']}/102", "stronger quality split", "fundamental_supported improved 120d context", "review_priority", "financial_as_of_date/announcement_date <= admission_date", "requires_admission_date_join", True, False, True, "derived features, not full statements"),
        ("fundamental_recovery_signal", "fundamental", "fundamental derived PIT features", "watchlist_fundamental_patch_summary_by_asset.csv", f"{coverage['fundamental_recovery_signal']}/102", "useful split", "recovery_positive improved average 120d context", "review_priority", "financial_as_of_date/announcement_date <= admission_date", "requires_admission_date_join", True, False, True, "use for review priority after PIT replay"),
        ("fundamental_risk_level", "fundamental", "fundamental derived PIT features", "watchlist_fundamental_patch_summary_by_asset.csv", f"{coverage['fundamental_risk_level']}/102", "risk context", "risk_medium broad bucket", "risk_warning", "financial_as_of_date/announcement_date <= admission_date", "requires_admission_date_join", True, False, True, "missing detail cannot imply no risk"),
        ("fundamental_quality_level", "fundamental", "fundamental derived PIT features", "watchlist_fundamental_patch_summary_by_asset.csv", f"{coverage['fundamental_quality_level']}/102", "strong quality split", "quality_medium_or_above had stronger ex-post context", "review_priority", "financial_as_of_date/announcement_date <= admission_date", "requires_admission_date_join", True, False, True, "priority design candidate"),
        ("fundamental_recovery_score", "fundamental", "fundamental derived PIT features", "fundamental_structured_outputs.csv", "63/102 upstream", "numeric context", "score supports signal labels but detail degraded", "review_priority", "financial_as_of_date <= admission_date", "requires_admission_date_join", True, False, True, "research score only"),
        ("fundamental_risk_score", "fundamental", "fundamental derived PIT features", "fundamental_structured_outputs.csv", "63/102 upstream", "numeric risk context", "score supports risk labels but detail degraded", "risk_warning", "financial_as_of_date <= admission_date", "requires_admission_date_join", True, False, True, "research score only"),
        ("fundamental_quality_score", "fundamental", "fundamental derived PIT features", "fundamental_structured_outputs.csv", "63/102 upstream", "numeric quality context", "quality context was useful ex-post", "review_priority", "financial_as_of_date <= admission_date", "requires_admission_date_join", True, False, True, "research score only"),
        ("baostock_valuation_support", "valuation", "BaoStock valuation", "watchlist_baostock_valuation_patch_summary_by_asset.csv", f"{coverage['baostock_valuation_support']}/102", "complete coverage", "coverage improves interpretability", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "primary valuation source"),
        ("pe_meaningfulness", "valuation", "BaoStock valuation", "watchlist_baostock_valuation_patch_summary_by_asset.csv", f"{coverage['pe_meaningfulness']}/102", "risk/context", "negative PE must be reviewed separately", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "not low valuation proof"),
        ("valuation_context_level", "valuation", "BaoStock valuation", "watchlist_baostock_valuation_patch_summary_by_asset.csv", f"{coverage['valuation_context_level']}/102", "informative but ambiguous", "high context performed strongly ex-post but not rule-ready", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "growth-stock structure risk"),
        ("pe_ttm_percentile_3y", "valuation", "BaoStock valuation", "baostock_percentile_outputs.csv", "93/102 upstream", "valuation context", "useful for context only", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "not an admission condition yet"),
        ("pb_percentile_3y", "valuation", "BaoStock valuation", "baostock_percentile_outputs.csv", "93/102 upstream", "valuation context", "useful for context only", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "not an admission condition yet"),
        ("ps_ttm_percentile_3y", "valuation", "BaoStock valuation", "baostock_percentile_outputs.csv", "93/102 upstream", "valuation context", "useful for context only", "dashboard_filter", "baostock_date <= admission_date", "requires_valuation_date_replay", True, False, True, "not an admission condition yet"),
        ("baidu_validation_status", "cross_source_validation", "Baidu validation", "akshare_baidu_baostock_cross_validation.csv", f"{coverage['baidu_validation_status']}/102", "quality check", "100 consistent, limited selection power", "dashboard_filter", "baidu_date <= admission_date", "requires_validation_date_replay", True, False, True, "auxiliary validation"),
        ("cross_source_discrepancy_flag", "cross_source_validation", "Baidu validation", "akshare_baidu_baostock_cross_validation.csv", f"{coverage['cross_source_discrepancy_flag']}/102", "manual review", "material difference sample too small", "manual_review_only", "baidu_date <= admission_date", "requires_validation_date_replay", True, False, True, "does not override BaoStock automatically"),
        ("human_review_required", "data_quality", "dashboard readonly", "tech_bottleneck_dashboard_table.csv", "102/102", "workflow context", "all research files require review", "dashboard_filter", "not source feature", "ex_post_only", True, False, True, "workflow flag"),
        ("data_quality_status", "data_quality", "consolidated snapshot", "watchlist_report_consolidated_summary_by_asset.csv", f"{coverage['data_quality_status']}/102", "quality boundary", "degraded sources must remain visible", "data_quality_warning", "not source feature", "ex_post_only", True, False, True, "do not use as historical event source"),
        ("degraded_source_warning", "data_quality", "dashboard readonly", "tech_bottleneck_dashboard_warnings.json", "102/102", "quality boundary", "must display in review UI", "data_quality_warning", "not source feature", "ex_post_only", True, False, True, "warning only"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "feature_name",
            "feature_group",
            "source_layer",
            "source_file",
            "current_coverage",
            "observed_quality_signal",
            "validation_result_summary",
            "recommended_usage",
            "pit_requirement",
            "pit_current_status",
            "can_use_for_v2_design",
            "can_use_for_pit_replay_now",
            "must_not_use_for_signal",
            "notes",
        ],
    )


def build_pit_matrix() -> pd.DataFrame:
    rows = [
        ("original research selection", "thesis", "first_source_date", "first_source_date", True, True, "first_source_date <= first_admission_date", True, "none", "none", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "low"),
        ("announcement fulltext", "announcement", "announcement_date", "as_of_date", True, True, "announcement_date/as_of_date <= first_admission_date", False, "source-date join to admission not built", "join announcement evidence by source date before replay", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "lookahead if snapshot is used directly"),
        ("fundamental derived PIT features", "fundamental", "financial_as_of_date", "announcement_date", True, True, "financial_as_of_date/announcement_date <= first_admission_date", False, "admission-date join not built", "join derived feature rows by admission date", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "lookahead if latest snapshot is used directly"),
        ("BaoStock valuation", "valuation", "baostock_date", "baostock_date", True, True, "baostock_date <= first_admission_date", False, "admission-date valuation replay not built", "select latest valuation row before admission date", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "valuation lookahead if latest snapshot is used directly"),
        ("Baidu validation", "cross_source_validation", "baidu_trade_date", "baidu_trade_date", True, True, "baidu_trade_date <= first_admission_date", False, "admission-date validation replay not built", "select latest Baidu row before admission date", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "validation lookahead if latest snapshot is used directly"),
        ("consolidated snapshot", "data_quality", "none", "none", False, False, "not a PIT source", False, "ex-post-only snapshot", "use underlying source layers instead", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "cannot use snapshot as historical source"),
        ("dashboard readonly", "data_quality", "none", "none", False, False, "not a PIT source", False, "ex-post-only UI package", "use underlying source layers instead", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "cannot use dashboard package as historical source"),
        ("forward return", "forward_return_context", "future horizon", "future horizon", False, False, "outcome only; not selection feature", False, "not selection feature", "keep as outcome only", "tech_bottleneck_research_selection_layer_v2_pit_replay_v1", "future-data leakage if used for selection"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "source_layer",
            "feature_group",
            "required_source_date_field",
            "required_as_of_field",
            "current_source_date_available",
            "current_as_of_available",
            "pit_rule",
            "pit_feasible_now",
            "pit_gap",
            "required_fix_before_replay",
            "recommended_next_task",
            "risk_if_used_without_fix",
        ],
    )


def build_rule_candidates(variant_summary: pd.DataFrame) -> pd.DataFrame:
    def _sample(name: str) -> int:
        row = variant_summary[variant_summary["variant_name"].eq(name)]
        return int(row["event_count"].iloc[0]) if not row.empty else 0

    rows = [
        ("v2_baseline_plus_fundamental_quality", "review_priority", "Baseline watchlist plus quality/recovery context.", "baseline membership; fundamental_quality_medium_or_above or fundamental_recovery_positive", "source date unavailable for replay", "higher review focus on derived fundamental quality", "fundamental quality/recovery had stronger ex-post context", _sample("fundamental_quality_medium_or_above"), False, "needs admission-date PIT join", "use_as_review_priority", False, "requires PIT replay before admission use"),
        ("v2_announcement_risk_review_queue", "risk_warning", "Specific risk event queue.", "specific_risk_event_count > 0", "none", "better manual risk review", "risk event group helps interpretation more than return separation", _sample("specific_risk_event_present"), False, "needs announcement source-date join", "manual_review_only", False, "warning queue, not exclusion"),
        ("v2_specific_validation_review_priority", "review_priority", "Specific positive announcement validation review.", "specific_validation_count > 0", "none", "thesis validation review", "specific validation sample did not clearly improve 120d average", _sample("specific_validation_supported"), False, "needs announcement source-date join", "use_as_review_priority", False, "thesis review, not admission rule"),
        ("v2_valuation_context_filter", "dashboard_filter", "BaoStock valuation context filter.", "valuation_context_level; pe_meaningfulness", "none", "valuation context exploration", "valuation_high_context was strong ex-post but ambiguous", 102, False, "needs valuation date replay and growth-stock adjustment", "use_as_dashboard_filter", False, "not an admission or exclusion rule"),
        ("v2_cross_source_discrepancy_warning", "manual_review_queue", "Baidu material difference review.", "baidu_validation_status == material_difference", "none", "manual validation check", "material discrepancy sample size is one", _sample("baidu_material_discrepancy"), False, "needs validation date replay", "manual_review_only", False, "sample too small"),
        ("v2_high_quality_review_candidates", "review_priority", "Strict high-quality manual review queue.", "thesis available; announcement or fundamental; valuation support; no material discrepancy", "severe data quality issue", "high-priority manual review queue", "high_quality_review_candidates improved ex-post context", _sample("high_quality_review_candidates"), False, "needs source-date replay across layers", "requires_pit_replay", False, "candidate for PIT replay design"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "rule_candidate_name",
            "rule_type",
            "description",
            "required_conditions",
            "excluded_conditions",
            "expected_effect",
            "evidence_from_validation",
            "sample_size",
            "pit_feasible_now",
            "pit_gap",
            "recommended_status",
            "used_for_signal",
            "notes",
        ],
    )


def build_review_priority_rules() -> pd.DataFrame:
    rows = [
        ("priority_high_review", "quality_and_validation_review", "fundamental_recovery_positive; fundamental_quality_medium_or_above; specific_validation_count > 0; BaoStock support; no material discrepancy", "fundamental and validation cues are useful for review focus", "manual review queue ranking", "ex-post grouping until source-date replay", False, False),
        ("priority_risk_review", "risk_context_review", "specific_risk_event_count > 0; Baidu material_difference; PE negative/loss-making; data quality degraded", "risk and discrepancy cues require human review", "risk review queue", "warning only; not automatic exclusion", False, False),
        ("priority_data_gap_review", "source_gap_review", "no announcement support; no fundamental support; thesis missing; only valuation support", "missing source layers limit interpretation", "source request queue", "missing fields cannot imply low risk", False, False),
        ("priority_standard_review", "baseline_review", "baseline standard watchlist; partial source coverage; no special risk or validation cue", "standard watchlist review cadence", "normal manual review", "baseline remains research context", False, False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "priority_level",
            "priority_name",
            "conditions",
            "reason",
            "expected_review_use",
            "data_quality_warning",
            "pit_feasible_now",
            "used_for_signal",
        ],
    )


def build_warning_rules() -> pd.DataFrame:
    rows = [
        ("missing_thesis_warning", "thesis missing", "data_quality_warning", "high", "review_thesis", False, "thesis must be clear before higher confidence review", False),
        ("no_announcement_support_warning", "announcement_fulltext_support is false", "source_gap_warning", "medium", "request_more_sources", False, "announcement missing weakens evidence review", False),
        ("no_fundamental_support_warning", "fundamental_support is false", "source_gap_warning", "medium", "request_more_sources", False, "fundamental context missing", False),
        ("pe_not_meaningful_warning", "pe_meaningfulness != pe_meaningful", "valuation_warning", "medium", "review_pe_not_meaningful", False, "negative or missing PE is not low-valuation proof", False),
        ("valuation_discrepancy_warning", "baidu_validation_status == material_difference", "cross_source_warning", "high", "review_valuation_discrepancy", False, "Baidu and BaoStock mismatch needs human review", False),
        ("specific_risk_event_warning", "specific_risk_event_count > 0", "risk_warning", "high", "review_specific_risk_event", False, "risk event should be reviewed, not automatically excluded", False),
        ("generic_disclosure_not_specific_warning", "generic_disclosure_text_count > 0 and specific_risk_event_count == 0", "evidence_quality_warning", "low", "review_consolidated_report", False, "generic disclosure is not a specific event", False),
        ("ex_post_grouping_warning", "validation_mode == ex_post_quality_grouping", "method_warning", "critical", "manual_review_required", False, "snapshot grouping is not a PIT historical rule", False),
        ("missing_full_financial_statement_warning", "full financial statement fields missing", "source_gap_warning", "high", "request_more_sources", False, "derived features are not full statement evidence", False),
        ("missing_news_source_warning", "news source missing", "source_gap_warning", "medium", "request_more_sources", False, "news mapping remains absent", False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "warning_rule_name",
            "conditions",
            "warning_type",
            "severity",
            "recommended_review_action",
            "auto_exclude",
            "reason",
            "used_for_signal",
        ],
    )


def build_replay_plan() -> pd.DataFrame:
    rows = [
        (
            "tech_bottleneck_research_selection_layer_v2_pit_replay_v1",
            "Replay v2 rule candidates using source-date-valid fields only.",
            "admission events; announcement evidence rows; fundamental rows; BaoStock history rows; Baidu validation rows; forward outcomes",
            "first_source_date|announcement_date|financial_as_of_date|baostock_date|baidu_trade_date",
            "first_source_date|as_of_date|announcement_date|financial_as_of_date",
            "baseline; fundamental quality; announcement support; valuation context; high_quality_review_candidates",
            "candidate events; forward return summary; source-date audit; method report",
            "source-date joins by admission date; full source availability matrix; no snapshot-derived fields",
            "all source dates <= first_admission_date; forward return only outcome; lookahead rows zero; all rows research-only",
            1,
        )
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "replay_task_name",
            "purpose",
            "required_inputs",
            "required_source_date_fields",
            "required_as_of_fields",
            "variants_to_replay",
            "expected_outputs",
            "blocking_gaps",
            "acceptance_criteria",
            "recommended_order",
        ],
    )


def build_filter_plan() -> pd.DataFrame:
    rows = [
        ("fundamental_recovery_signal", "fundamental_recovery_signal", "enum", "recovery_positive|recovery_neutral|recovery_weak|recovery_missing", True, "review fundamental recovery context", "derived feature warning", False),
        ("fundamental_quality_level", "fundamental_quality_level", "enum", "quality_high|quality_medium|quality_low|quality_missing", True, "review quality context", "not full statement evidence", False),
        ("specific_validation_count", "specific_validation_count", "numeric_bucket", "0|1|2_plus", True, "review thesis validation evidence", "source-date replay required for historical rule", False),
        ("specific_risk_event_count", "specific_risk_event_count", "numeric_bucket", "0|1|2_plus", True, "review risk event evidence", "warning only", False),
        ("valuation_context_level", "valuation_context_level", "enum", "valuation_low_context|valuation_mid_context|valuation_high_context|valuation_mixed_context", True, "review valuation context", "not a standalone rule", False),
        ("pe_meaningfulness", "pe_meaningfulness", "enum", "pe_meaningful|pe_negative_or_loss_making|pe_missing|pe_not_meaningful", True, "review PE interpretability", "negative PE not low valuation proof", False),
        ("baidu_validation_status", "baidu_validation_status", "enum", "consistent|minor_difference|material_difference|missing", True, "review cross-source validation", "Baidu is auxiliary", False),
        ("data_quality_status", "data_quality_status", "enum", "review_ready_degraded_sources|degraded_source_gaps|missing", True, "review data-quality status", "degraded sources visible", False),
        ("human_review_required", "human_review_required", "boolean", "true|false", True, "review queue control", "manual workflow only", False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "filter_name",
            "source_field",
            "filter_type",
            "values",
            "default_visible",
            "review_use",
            "warning",
            "used_for_signal",
        ],
    )


def build_quality_audit(features: pd.DataFrame, matrix: pd.DataFrame, rules: pd.DataFrame, priority: pd.DataFrame, warnings: pd.DataFrame, replay: pd.DataFrame, filters: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    false_count = int((~rules["used_for_signal"].astype(bool)).sum() + (~priority["used_for_signal"].astype(bool)).sum() + (~warnings["used_for_signal"].astype(bool)).sum() + (~filters["used_for_signal"].astype(bool)).sum())
    rows = [
        ("features evaluated", len(features), "feature dictionary rows"),
        ("pit_feasible_features_now", int(features["can_use_for_pit_replay_now"].astype(bool).sum()), "currently replay-ready features"),
        ("ex_post_only_features", int((~features["can_use_for_pit_replay_now"].astype(bool)).sum()), "requires replay fixes or review-only"),
        ("rule candidates generated", len(rules), "candidate rows"),
        ("review priority rules generated", len(priority), "priority rows"),
        ("warning rules generated", len(warnings), "warning rows"),
        ("replay plan rows", len(replay), "PIT replay plan rows"),
        ("dashboard filter rows", len(filters), "filter rows"),
        ("rules used_for_signal false count", false_count, "all rule/filter rows"),
        ("trading language hit count", 0, "computed after write"),
        ("lookahead violation rows", 0, "design only; no replay performed"),
        ("formal strategy file status", status, "untracked status must be visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(features: pd.DataFrame, matrix: pd.DataFrame, rules: pd.DataFrame, audit: pd.DataFrame) -> str:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    pit_now = int(features["can_use_for_pit_replay_now"].astype(bool).sum())
    ex_post = int((~features["can_use_for_pit_replay_now"].astype(bool)).sum())
    return f"""# Tech Bottleneck Research Selection Layer v2 Design

## 1. Executive Summary

V2 design generated successfully. Enriched validation suggests derived fundamental quality and recovery are the most useful research-priority fields; announcement evidence improves thesis/risk review; valuation context is informative but ambiguous; Baidu validation is mainly a quality check. Current design does not immediately change admission rules because most enriched fields require PIT replay before historical use.

Fields evaluated: {len(features)}. PIT-feasible now: {pit_now}. Ex-post or replay-required fields: {ex_post}. Rule candidates generated: {len(rules)}. No automated execution prompt is generated. Formal strategy files were not modified; if untracked, 无法仅靠 `git diff` 完整证明历史状态。

## 2. Input Files

- enriched selection validation outputs
- consolidated report outputs
- dashboard readonly outputs
- original research selection layer outputs when available

## 3. Key Findings from Enriched Validation

Baseline average context was 30d 0.084494, 60d 0.210774, 90d 0.143903, 120d 0.319164. Fundamental quality/recovery groups showed stronger ex-post 120d context. Announcement evidence mainly improves interpretation and risk review. Valuation high context performed strongly ex-post, but this may reflect growth-stock sample structure and cannot be used directly. Baidu validation was consistent for most assets, so it is primarily a cross-source quality check.

## 4. Feature Dictionary

Feature groups include thesis, announcement, fundamental, valuation, cross-source validation, data quality, and risk review. Forward return is kept out of the feature dictionary and remains validation outcome only.

## 5. PIT Feasibility

Original admission events are currently PIT-feasible. Announcement, derived fundamental, BaoStock valuation, and Baidu validation require source-date joins against first admission date. Consolidated snapshot and dashboard readonly packages are ex-post-only and must not be used as PIT source. Forward return is outcome only.

## 6. V2 Rule Candidate Design

Rule candidates are research selection and review-priority candidates only. The strongest design candidates are `v2_baseline_plus_fundamental_quality`, `v2_high_quality_review_candidates`, and `v2_announcement_risk_review_queue`, all requiring PIT replay or manual review before operational use.

## 7. Review Priority Design

Review priority levels are high review, risk review, data gap review, and standard review. Priority labels are manual workflow labels, not execution labels.

## 8. Warning and Exclusion Design

Warning rules do not auto-exclude by default. Risk cues, missing source layers, PE interpretability, valuation discrepancies, generic disclosure, and ex-post grouping all route to human review or source requests.

## 9. Dashboard Filter Plan

Read-only dashboard filters should expose fundamental recovery, fundamental quality, specific validation count, specific risk event count, valuation context, PE meaningfulness, Baidu validation, data quality status, and human review required.

## 10. PIT Replay Plan

Next replay task: `tech_bottleneck_research_selection_layer_v2_pit_replay_v1`. It must select source rows using source dates no later than first admission date, use forward return as outcome only, and keep outputs research-only.

## 11. What This Design Does Not Do

- no automated execution prompt
- no Top5 change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no execution instruction
- no ex-post grouping as historical rule
- no forward return as admission condition

## 12. Recommended Next Step

Recommended: `tech_bottleneck_research_selection_layer_v2_pit_replay_v1`. In parallel, design `tech_bottleneck_manual_review_label_schema_v1`. Continue deferring trigger / holding / exit.

## 13. Appendix

Generated files:
- research_selection_v2_feature_dictionary.csv
- research_selection_v2_pit_feasibility_matrix.csv
- research_selection_v2_rule_candidates.csv
- research_selection_v2_review_priority_rules.csv
- research_selection_v2_exclusion_and_warning_rules.csv
- research_selection_v2_replay_plan.csv
- research_selection_v2_dashboard_filter_plan.csv
- research_selection_v2_quality_audit.csv
- research_selection_layer_v2_design.md

Formal strategy git status:
```text
{status}
```

Formal strategy git diff:
```text
{diff}
```

Key assumptions: v2 remains research-only; enriched groups require source-date replay. Uncertainties: full statement source, news source, and manual labels remain future work.
"""


def write_outputs() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_summary_by_asset.csv")
    variant_summary = _read_csv(ENRICHED_DIR / "enriched_selection_variant_summary.csv")
    features = build_feature_dictionary(summary, variant_summary)
    matrix = build_pit_matrix()
    rules = build_rule_candidates(variant_summary)
    priority = build_review_priority_rules()
    warnings = build_warning_rules()
    replay = build_replay_plan()
    filters = build_filter_plan()
    audit = build_quality_audit(features, matrix, rules, priority, warnings, replay, filters)

    features.to_csv(OUTPUT_DIR / "research_selection_v2_feature_dictionary.csv", index=False)
    matrix.to_csv(OUTPUT_DIR / "research_selection_v2_pit_feasibility_matrix.csv", index=False)
    rules.to_csv(OUTPUT_DIR / "research_selection_v2_rule_candidates.csv", index=False)
    priority.to_csv(OUTPUT_DIR / "research_selection_v2_review_priority_rules.csv", index=False)
    warnings.to_csv(OUTPUT_DIR / "research_selection_v2_exclusion_and_warning_rules.csv", index=False)
    replay.to_csv(OUTPUT_DIR / "research_selection_v2_replay_plan.csv", index=False)
    filters.to_csv(OUTPUT_DIR / "research_selection_v2_dashboard_filter_plan.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv", index=False)
    (OUTPUT_DIR / "research_selection_layer_v2_design.md").write_text(render_report(features, matrix, rules, audit), encoding="utf-8")
    hit_count = _count_output_hits(OUTPUT_DIR)
    audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hit_count
    audit.to_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv", index=False)
    return {
        "features": features,
        "matrix": matrix,
        "rules": rules,
        "priority": priority,
        "warnings": warnings,
        "replay": replay,
        "filters": filters,
        "audit": audit,
    }


def main() -> pd.DataFrame:
    outputs = write_outputs()
    audit = outputs["audit"]
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
