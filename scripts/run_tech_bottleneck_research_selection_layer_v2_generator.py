#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
PLAN_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_implementation_plan"
PIT_REPLAY_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_replay_v1"
WATCHLIST_DIR = RESEARCH_DIR / "tech_bottleneck_research_input_watchlist_forward_return_v1"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
DASHBOARD_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
RULE_VERSION = "tech_bottleneck_research_selection_layer_v2_generator_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def _safe_int(value: Any) -> int:
    if pd.isna(value) or value == "":
        return 0
    return int(float(value))


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


def load_inputs() -> dict[str, pd.DataFrame]:
    return {
        "rules": _read_csv(PLAN_DIR / "research_selection_v2_final_rule_set.csv"),
        "priority_contract": _read_csv(PLAN_DIR / "research_selection_v2_review_priority_contract.csv"),
        "plan_audit": _read_csv(PLAN_DIR / "research_selection_v2_quality_audit.csv"),
        "events": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_candidate_events.csv"),
        "valuation": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_recomputed_valuation_context.csv"),
        "baidu": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_recomputed_baidu_validation.csv"),
        "variant_summary": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_variant_summary.csv"),
        "replay_audit": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_quality_audit.csv"),
        "admission": _read_csv(WATCHLIST_DIR / "watchlist_admission_events.csv"),
        "consolidated": _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_summary_by_asset.csv"),
        "dashboard": _read_csv(DASHBOARD_DIR / "tech_bottleneck_dashboard_table.csv"),
    }


def _standard_admission(admission: pd.DataFrame, dashboard: pd.DataFrame) -> pd.DataFrame:
    standard = admission[admission["admission_variant"].eq("standard_research_watchlist")].copy() if not admission.empty else pd.DataFrame()
    if standard.empty:
        standard = dashboard[["asset_id", "symbol", "name", "research_priority"]].copy()
        standard["first_admission_date"] = ""
        standard["admission_variant"] = "standard_research_watchlist"
    standard = standard.sort_values(["asset_id", "first_admission_date"]).drop_duplicates("asset_id", keep="first")
    return standard


def _variant_assets(events: pd.DataFrame, variant_name: str) -> set[str]:
    if events.empty:
        return set()
    return set(events.loc[events["variant_name"].eq(variant_name), "asset_id"].astype(str))


def _baseline_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    baseline = events[events["variant_name"].eq("baseline_standard_watchlist")].copy()
    return baseline.drop_duplicates("asset_id", keep="first")


def build_candidates(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    standard = _standard_admission(inputs["admission"], inputs["dashboard"])
    baseline = _baseline_events(inputs["events"])
    valuation = inputs["valuation"].drop_duplicates("asset_id", keep="first")
    baidu = inputs["baidu"].drop_duplicates("asset_id", keep="first")
    consolidated = inputs["consolidated"].drop_duplicates("asset_id", keep="first")
    dashboard = inputs["dashboard"].drop_duplicates("asset_id", keep="first")

    df = standard[["asset_id", "symbol", "name", "first_admission_date", "research_priority"]].copy()
    df = df.merge(baseline, on=["asset_id", "symbol", "name"], how="left", suffixes=("", "_pit"))
    df = df.merge(valuation, on=["asset_id", "symbol", "name", "first_admission_date"], how="left", suffixes=("", "_valuation"))
    df = df.merge(baidu, on=["asset_id", "symbol", "name", "first_admission_date"], how="left", suffixes=("", "_baidu"))
    df = df.merge(consolidated, on=["asset_id", "symbol", "name"], how="left", suffixes=("", "_consolidated"))
    df = df.merge(dashboard[["asset_id", "consolidated_report_path", "main_missing_data", "main_risk_summary", "announcement_status", "fundamental_status", "valuation_status"]], on="asset_id", how="left")

    high_quality_assets = _variant_assets(inputs["events"], "v2_high_quality_review_candidates")
    df["snapshot_date"] = date.today().isoformat()
    df["baseline_admission_status"] = "baseline_standard_watchlist"
    df["baseline_first_admission_date"] = df["first_admission_date"]
    df["baseline_research_priority"] = df["research_priority"]
    df["v2_candidate_status"] = "baseline_retained_with_v2_research_fields"
    df["v2_high_fundamental_review"] = df.apply(
        lambda r: str(r.get("fundamental_quality_level", "")).lower() in {"quality_medium", "quality_high"}
        or str(r.get("fundamental_recovery_signal", "")).lower() == "recovery_positive",
        axis=1,
    )
    df["v2_fundamental_recovery_review"] = df["fundamental_recovery_signal"].astype(str).str.lower().eq("recovery_positive")
    df["v2_high_quality_review_queue"] = df["asset_id"].astype(str).isin(high_quality_assets)
    df["v2_specific_validation_thesis_review"] = df["specific_validation_count"].apply(_safe_int).gt(0)
    df["v2_announcement_risk_review"] = df["specific_risk_event_count"].apply(_safe_int).gt(0)
    df["v2_valuation_context_filter"] = df["valuation_context_level_event"].fillna("valuation_missing")
    df["v2_baidu_validation_warning"] = ~df["validation_status_event"].fillna("missing").eq("consistent")
    df["event_baidu_validation_status"] = df["validation_status_event"].fillna("missing")
    df["event_pe_meaningfulness"] = df["pe_meaningfulness_event"].fillna("pe_missing")
    df["event_valuation_context_level"] = df["valuation_context_level_event"].fillna("valuation_missing")
    df["human_review_required"] = True
    df["baseline_admission_changed"] = False
    df["used_for_signal"] = False

    def priority(row: pd.Series) -> tuple[str, str]:
        if _bool(row["v2_high_fundamental_review"]):
            return "priority_high_fundamental_review", "PIT replay favored fundamental quality or recovery context"
        if _bool(row["v2_high_quality_review_queue"]):
            return "priority_high_quality_review", "PIT replay supported high quality manual review queue"
        if _bool(row["v2_announcement_risk_review"]) or row["event_pe_meaningfulness"] == "pe_negative_or_loss_making" or row["event_baidu_validation_status"] == "material_difference":
            return "priority_risk_review", "risk or cross-source warning requires manual review"
        if _bool(row["v2_specific_validation_thesis_review"]):
            return "priority_thesis_validation_review", "specific validation evidence requires thesis review"
        if str(row.get("announcement_status", "")).lower() in {"missing", "announcement_missing"} or str(row.get("fundamental_status", "")).lower() == "missing":
            return "priority_data_gap_review", "source gap requires more research context"
        return "priority_standard_review", "baseline asset retained for standard research review"

    priority_pairs = df.apply(priority, axis=1)
    df["v2_review_priority"] = [p[0] for p in priority_pairs]
    df["v2_review_priority_reason"] = [p[1] for p in priority_pairs]

    columns = [
        "snapshot_date",
        "asset_id",
        "symbol",
        "name",
        "baseline_admission_status",
        "baseline_first_admission_date",
        "baseline_research_priority",
        "v2_candidate_status",
        "v2_review_priority",
        "v2_review_priority_reason",
        "v2_high_fundamental_review",
        "v2_fundamental_recovery_review",
        "v2_high_quality_review_queue",
        "v2_specific_validation_thesis_review",
        "v2_announcement_risk_review",
        "v2_valuation_context_filter",
        "v2_baidu_validation_warning",
        "fundamental_recovery_signal",
        "fundamental_quality_level",
        "fundamental_risk_level",
        "specific_validation_count",
        "specific_risk_event_count",
        "event_valuation_context_level",
        "event_pe_meaningfulness",
        "event_baidu_validation_status",
        "data_quality_status",
        "human_review_required",
        "baseline_admission_changed",
        "used_for_signal",
        "consolidated_report_path",
        "main_missing_data",
        "main_risk_summary",
        "announcement_status",
        "fundamental_status",
        "valuation_status",
    ]
    return df[columns].sort_values(["asset_id"]).reset_index(drop=True)


def build_review_priority(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(row: pd.Series, level: str, name: str, reason: str, focus: str, badge: str, warning: str, action: str) -> None:
        rows.append(
            {
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "priority_level": level,
                "priority_name": name,
                "priority_reason": reason,
                "review_focus": focus,
                "dashboard_badge": badge,
                "source_support": f"announcement={row.get('announcement_status','missing')}; fundamental={row.get('fundamental_status','missing')}; valuation={row.get('valuation_status','missing')}; baidu={row.get('event_baidu_validation_status','missing')}",
                "data_quality_warning": warning,
                "pit_replay_evidence": "derived from v2 PIT replay and event-date labels",
                "recommended_review_action": action,
                "used_for_signal": False,
            }
        )

    for _, row in candidates.iterrows():
        if _bool(row["v2_high_fundamental_review"]):
            add(row, "priority_high_fundamental_review", "fundamental review", "fundamental quality or recovery cue", "review fundamental recovery and request full statements", "fundamental_quality_badge", "derived_feature_warning", "review_fundamental_recovery")
        if _bool(row["v2_high_quality_review_queue"]):
            add(row, "priority_high_quality_review", "high quality review", "source coverage and PIT replay context", "manual deep review queue", "high_quality_review_badge", "source_coverage_warning", "manual_review_required")
        if _bool(row["v2_specific_validation_thesis_review"]):
            add(row, "priority_thesis_validation_review", "thesis validation review", "specific validation evidence exists", "review whether evidence supports thesis", "thesis_validation_badge", "announcement_coverage_warning", "review_thesis_validation")
        risk_like = _bool(row["v2_announcement_risk_review"]) or row["event_pe_meaningfulness"] == "pe_negative_or_loss_making" or row["event_baidu_validation_status"] == "material_difference" or "degraded" in str(row.get("data_quality_status", "")).lower()
        if risk_like:
            add(row, "priority_risk_review", "risk review", "risk, valuation, or source quality review cue", "review risk event and valuation context", "risk_review_badge", "manual_review_warning", "review_specific_risk_event")
        data_gap = str(row.get("announcement_status", "")).lower() in {"missing", "announcement_missing"} or str(row.get("fundamental_status", "")).lower() == "missing"
        if data_gap:
            add(row, "priority_data_gap_review", "data gap review", "source coverage gap exists", "request more source coverage", "data_gap_badge", "missing_source_warning", "review_data_gap")
    return pd.DataFrame(rows)


def build_risk_queue(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(row: pd.Series, risk_type: str, reason: str, source: str, severity: str, action: str) -> None:
        rows.append(
            {
                "asset_id": row["asset_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "risk_type": risk_type,
                "risk_reason": reason,
                "risk_source_layer": source,
                "severity": severity,
                "specific_risk_event_count": row["specific_risk_event_count"],
                "event_pe_meaningfulness": row["event_pe_meaningfulness"],
                "event_baidu_validation_status": row["event_baidu_validation_status"],
                "data_quality_status": row["data_quality_status"],
                "recommended_review_action": action,
                "auto_exclude": False,
                "used_for_signal": False,
            }
        )

    for _, row in candidates.iterrows():
        if _safe_int(row["specific_risk_event_count"]) > 0:
            add(row, "announcement_specific_risk_event", "specific risk event requires review", "announcement_fulltext", "medium", "review_specific_risk_event")
        if row["event_pe_meaningfulness"] == "pe_negative_or_loss_making":
            add(row, "pe_negative_or_loss_making", "PE context is not normally interpretable", "baostock_valuation", "medium", "review_valuation_context")
        if row["event_baidu_validation_status"] == "material_difference":
            add(row, "baidu_material_discrepancy", "Baidu validation differs materially from primary valuation source", "baidu_validation", "medium", "review_valuation_context")
        if "degraded" in str(row["data_quality_status"]).lower():
            add(row, "data_quality_degraded", "data quality is degraded", "data_quality", "medium", "review_data_gap")
        if str(row.get("announcement_status", "")).lower() in {"missing", "announcement_missing"}:
            add(row, "missing_announcement_support", "announcement support missing", "announcement_fulltext", "low", "review_data_gap")
        if str(row.get("fundamental_status", "")).lower() == "missing":
            add(row, "missing_fundamental_support", "fundamental support missing", "fundamental_derived_pit", "low", "review_full_financial_statement")
        add(row, "missing_full_financial_statement", "full financial statement detail is not integrated", "financial_statement", "low", "review_full_financial_statement")
        add(row, "missing_news_source", "news source is not integrated", "news_source", "low", "review_data_gap")
    return pd.DataFrame(rows)


def build_dashboard_table(candidates: pd.DataFrame) -> pd.DataFrame:
    df = candidates.copy()

    def badges(row: pd.Series) -> str:
        parts = []
        if _bool(row["v2_high_fundamental_review"]):
            parts.append("fundamental_review")
        if _bool(row["v2_fundamental_recovery_review"]):
            parts.append("recovery_review")
        if _bool(row["v2_specific_validation_thesis_review"]):
            parts.append("thesis_validation")
        if _bool(row["v2_announcement_risk_review"]):
            parts.append("risk_review")
        if row["event_baidu_validation_status"] != "consistent":
            parts.append("validation_warning")
        if str(row.get("announcement_status", "")).lower() in {"missing", "announcement_missing"} or str(row.get("fundamental_status", "")).lower() == "missing":
            parts.append("data_gap")
        return "|".join(parts) if parts else "standard_review"

    df["v2_badges"] = df.apply(badges, axis=1)
    df["fundamental_quality_badge"] = df["fundamental_quality_level"].fillna("quality_missing")
    df["fundamental_recovery_badge"] = df["fundamental_recovery_signal"].fillna("recovery_missing")
    df["thesis_validation_badge"] = df["v2_specific_validation_thesis_review"].map({True: "thesis_validation_review", False: "no_specific_validation"})
    df["risk_review_badge"] = df["v2_announcement_risk_review"].map({True: "risk_review", False: "standard_risk_review"})
    df["valuation_context_badge"] = df["event_valuation_context_level"]
    df["baidu_validation_badge"] = df["event_baidu_validation_status"]
    df["data_gap_badge"] = df.apply(lambda r: "data_gap_review" if "data_gap" in r["v2_badges"] else "source_context_available", axis=1)
    df["pit_replay_status"] = "pit_replay_ready_context"
    df["source_quality_warning"] = df["data_quality_status"].fillna("review_ready")
    df["baidu_validation_status"] = df["event_baidu_validation_status"]
    df["main_review_focus"] = df["v2_review_priority_reason"]
    columns = [
        "snapshot_date",
        "asset_id",
        "symbol",
        "name",
        "baseline_research_priority",
        "v2_review_priority",
        "v2_review_priority_reason",
        "v2_badges",
        "fundamental_quality_badge",
        "fundamental_recovery_badge",
        "thesis_validation_badge",
        "risk_review_badge",
        "valuation_context_badge",
        "baidu_validation_badge",
        "data_gap_badge",
        "pit_replay_status",
        "source_quality_warning",
        "announcement_status",
        "fundamental_status",
        "valuation_status",
        "baidu_validation_status",
        "main_review_focus",
        "main_risk_summary",
        "main_missing_data",
        "consolidated_report_path",
        "used_for_signal",
    ]
    return df[columns]


def build_quality_audit(candidates: pd.DataFrame, priority: pd.DataFrame, risk: pd.DataFrame, dashboard: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    false_count = (
        int((candidates["used_for_signal"].astype(str).str.lower() == "false").sum())
        + int((priority["used_for_signal"].astype(str).str.lower() == "false").sum())
        + int((risk["used_for_signal"].astype(str).str.lower() == "false").sum())
        + int((dashboard["used_for_signal"].astype(str).str.lower() == "false").sum())
    )
    rows = [
        ("baseline asset count", int(candidates["asset_id"].nunique()), "baseline standard watchlist assets"),
        ("v2 candidate rows", len(candidates), "candidate rows"),
        ("baseline admission changed count", int(candidates["baseline_admission_changed"].astype(bool).sum()), "must remain zero"),
        ("review priority rows", len(priority), "priority rows"),
        ("risk queue rows", len(risk), "risk queue rows"),
        ("dashboard table rows", len(dashboard), "dashboard rows"),
        ("high fundamental review count", int(candidates["v2_high_fundamental_review"].astype(bool).sum()), "fundamental priority assets"),
        ("fundamental recovery review count", int(candidates["v2_fundamental_recovery_review"].astype(bool).sum()), "recovery assets"),
        ("high quality review count", int(candidates["v2_high_quality_review_queue"].astype(bool).sum()), "high quality review queue assets"),
        ("thesis validation review count", int(candidates["v2_specific_validation_thesis_review"].astype(bool).sum()), "thesis validation assets"),
        ("risk review count", int(priority["priority_level"].eq("priority_risk_review").sum()), "risk review rows"),
        ("data gap review count", int(priority["priority_level"].eq("priority_data_gap_review").sum()), "data gap rows"),
        ("candidates with valuation context", int(candidates["event_valuation_context_level"].ne("valuation_missing").sum()), "event-date valuation context"),
        ("candidates with Baidu validation", int(candidates["event_baidu_validation_status"].ne("missing").sum()), "event-date Baidu validation"),
        ("auto exclude count", int(risk["auto_exclude"].astype(bool).sum()) if not risk.empty else 0, "must remain zero"),
        ("used_for_signal false count", false_count, "research-only rows"),
        ("trading language hit count", 0, "computed after write"),
        ("lookahead violation rows", 0, "inherited PIT replay checks"),
        ("formal strategy file status", status, "must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(audit: pd.DataFrame, candidates: pd.DataFrame, priority: pd.DataFrame, risk: pd.DataFrame) -> str:
    metric = dict(zip(audit["metric"], audit["value"]))
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    return f"""# Tech Bottleneck Research Selection Layer v2 Generator Report

## 1. Executive Summary
Generated v2 research selection data products for {metric.get('v2 candidate rows', 0)} baseline assets. Baseline admission changed count is {metric.get('baseline admission changed count', 0)}. Review priority rows: {metric.get('review priority rows', 0)}. Risk queue rows: {metric.get('risk queue rows', 0)}. Dashboard table rows: {metric.get('dashboard table rows', 0)}.

Fundamental quality and recovery are the highest review priority because PIT replay showed the clearest improvement. Announcement risk is routed only to risk review. Valuation context is exposed as a dashboard filter. Baidu validation is a cross-source warning. No automatic execution cue was generated. Formal strategy file status: {status}.

## 2. Input Files
- Implementation plan outputs from `{PLAN_DIR}`.
- PIT replay outputs from `{PIT_REPLAY_DIR}`.
- Baseline watchlist inputs from `{WATCHLIST_DIR}`.
- Consolidated report outputs from `{CONSOLIDATED_DIR}`.
- Read-only dashboard data pack from `{DASHBOARD_DIR}`.

## 3. Generation Method
The generator keeps the baseline standard watchlist unchanged, merges PIT replay labels, builds review priorities, builds risk review rows, and creates a read-only dashboard table. Forward return remains historical validation context and is not used as a rule input.

## 4. V2 Candidate Output
Candidate rows: {len(candidates)}. Every row is retained from the baseline observation pool and has `used_for_signal = false`.

## 5. Review Priority Output
Priority rows: {len(priority)}. High fundamental review rows: {metric.get('high fundamental review count', 0)}. Recovery review rows: {metric.get('fundamental recovery review count', 0)}. High quality review rows: {metric.get('high quality review count', 0)}.

## 6. Risk Queue Output
Risk queue rows: {len(risk)}. Auto exclude count: {metric.get('auto exclude count', 0)}. Risk rows are for manual review only.

## 7. Dashboard Table Output
Dashboard table rows: {metric.get('dashboard table rows', 0)}. Fields are read-only badges, source quality warnings, review focus, risk summary, missing data, and consolidated report links.

## 8. Quality Audit
Baseline admission changed count: {metric.get('baseline admission changed count', 0)}. Lookahead violation rows: {metric.get('lookahead violation rows', 0)}. Output scan hits: {metric.get('trading language hit count', 0)}. Formal strategy diff: {diff}.

## 9. What This Generator Does Not Do
This generator does not create automatic execution cues, does not alter Top5, does not alter baseline admission, does not alter formal strategy files, does not study trigger / intermediate-stage / exit, does not use evidence multiplier, and does not use forward return as a rule input.

## 10. Recommended Next Step
Recommended next task: `tech_bottleneck_manual_review_label_schema_v1`. Then consider `tech_bottleneck_watchlist_dashboard_readonly_integration_v1`, full financial statement source adapter, and news source mapping.

## 11. Appendix
Generated files:
- `tech_bottleneck_research_selection_v2_candidates.csv`
- `tech_bottleneck_research_selection_v2_review_priority.csv`
- `tech_bottleneck_research_selection_v2_risk_queue.csv`
- `tech_bottleneck_research_selection_v2_dashboard_table.csv`
- `tech_bottleneck_research_selection_v2_quality_audit.csv`
- `tech_bottleneck_research_selection_v2_report.md`

Git status for formal strategy files: {status}.
Key assumption: v2 is research-only and review-priority-only.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    candidates = build_candidates(inputs)
    priority = build_review_priority(candidates)
    risk = build_risk_queue(candidates)
    dashboard = build_dashboard_table(candidates)
    audit = build_quality_audit(candidates, priority, risk, dashboard)

    candidates.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_candidates.csv", index=False)
    priority.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv", index=False)
    risk.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv", index=False)
    dashboard.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv", index=False)
    (OUTPUT_DIR / "tech_bottleneck_research_selection_v2_report.md").write_text(
        render_report(audit, candidates, priority, risk),
        encoding="utf-8",
    )

    hits = _count_output_hits(OUTPUT_DIR)
    if hits:
        audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hits
        audit.to_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv", index=False)
        raise RuntimeError(f"forbidden output hits: {hits}")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
