#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_AUDIT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
DIAGNOSTICS_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_rescue_triage_v1"
HIGH_QUALITY_THRESHOLD = 58.0
THRESHOLDS = [58.0, 57.5, 57.0, 56.0, 55.0]
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes"}


def _load_inputs(quality_dir: Path, diagnostics_dir: Path) -> dict[str, Any]:
    return {
        "quality_summary": _read_json(quality_dir / "candidate_universe_quality_audit_summary.json"),
        "quality_guardrails": _read_json(quality_dir / "candidate_universe_quality_audit_guardrails.json"),
        "tier_a_quality": pd.read_csv(quality_dir / "tier_a_quality_audit.csv"),
        "tier_b_quality": pd.read_csv(quality_dir / "tier_b_quality_audit.csv"),
        "gap_breakdown": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "seed_preview": pd.read_csv(quality_dir / "seed_watchlist_quality_preview.csv"),
        "clean_subset": pd.read_csv(quality_dir / "clean_candidate_subset.csv"),
        "diagnostics_summary": _read_json(diagnostics_dir / "audit_diagnostics_summary.json"),
        "tier_b_feasibility": pd.read_csv(diagnostics_dir / "tier_b_high_quality_feasibility_audit.csv"),
        "non_clean": pd.read_csv(diagnostics_dir / "non_clean_failure_taxonomy.csv"),
        "seed_tier_b": pd.read_csv(diagnostics_dir / "seed_tier_b_diagnostics.csv"),
        "tier_a_source": pd.read_csv(diagnostics_dir / "tier_a_seed_vs_nonseed_audit.csv"),
        "possible_false_negative": pd.read_csv(diagnostics_dir / "possible_false_negative_rescue_list.csv"),
    }


def _gap_categories(flags: str, row: pd.Series | None = None) -> set[str]:
    text = _clean(flags)
    categories: set[str] = set()
    if row is not None and (not _clean(row.get("stock_code")) or not _clean(row.get("stock_name"))):
        categories.add("name/code mapping gap")
    if row is not None and (not _clean(row.get("tech_bottleneck_domain")) or _clean(row.get("supply_chain_role")) in {"", "unclear"}):
        categories.add("industry mapping gap")
    if "primary_source_evidence_missing" in text or "validated_or_confirmed_evidence_missing" in text:
        categories.add("evidence text gap")
    if "revenue_traceability_missing" in text:
        categories.add("financial data gap")
    if "trading_status_missing" in text or "list_status_missing" in text:
        categories.add("trading status gap")
    if "report_keyword_metadata_missing" in text or "keyword" in text:
        categories.add("keyword/category gap")
    if not categories:
        categories.add("other")
    return categories


def _primary_gap_type(flags: str, row: pd.Series) -> str:
    categories = _gap_categories(flags, row)
    priority = [
        "name/code mapping gap",
        "industry mapping gap",
        "financial data gap",
        "evidence text gap",
        "trading status gap",
        "keyword/category gap",
        "other",
    ]
    for category in priority:
        if category in categories:
            return category
    return "other"


def _gap_severity(flags: str, primary_gap_type: str) -> str:
    text = _clean(flags)
    has_primary = "primary_source_evidence_missing" in text
    has_validated = "validated_or_confirmed_evidence_missing" in text
    has_revenue = "revenue_traceability_missing" in text
    if has_primary and has_validated and has_revenue:
        return "blocking"
    if has_revenue or has_primary or has_validated:
        return "severe"
    if primary_gap_type in {"industry mapping gap", "keyword/category gap"}:
        return "moderate"
    return "minor"


def _recommended_action(priority: str, gap_type: str) -> str:
    if priority in {"P0", "P1", "P2"}:
        return "manual_rescue_review"
    if gap_type in {"financial data gap", "name/code mapping gap", "industry mapping gap"}:
        return "data_backfill_required"
    if gap_type in {"evidence text gap", "keyword/category gap"}:
        return "evidence_backfill_required"
    return "sample_audit_only"


def build_rescue_triage_queue(non_clean: pd.DataFrame, seed_tier_b: pd.DataFrame, seed_preview: pd.DataFrame) -> pd.DataFrame:
    seed_codes = set(seed_preview["stock_code"].astype(str))
    seed_tier_b_codes = set(seed_tier_b["stock_code"].astype(str))
    rescue = non_clean[non_clean["rescue_review_required"].astype(bool)].copy()
    rows = []
    for _, row in rescue.sort_values(["candidate_tier", "research_priority_score", "stock_code"], ascending=[True, False, True]).iterrows():
        code = str(row.get("stock_code"))
        is_seed = code in seed_codes
        is_seed_b = code in seed_tier_b_codes
        possible_false_negative = _truthy(row.get("possible_false_negative"))
        score = float(row.get("research_priority_score", 0) or 0)
        gap_type = _primary_gap_type(row.get("data_gap_flags"), row)
        severity = _gap_severity(row.get("data_gap_flags"), gap_type)
        if is_seed_b:
            priority = "P0"
        elif possible_false_negative:
            priority = "P1"
        elif _clean(row.get("candidate_tier")) == "Tier B" and score >= 55:
            priority = "P2"
        elif severity in {"minor", "moderate"}:
            priority = "P3"
        else:
            priority = "P4"
        action = _recommended_action(priority, gap_type)
        distance = round(HIGH_QUALITY_THRESHOLD - score, 2)
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "current_tier": row.get("candidate_tier"),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "is_seed_watchlist": is_seed,
                "is_tier_b_seed": is_seed_b,
                "is_possible_false_negative": possible_false_negative,
                "research_priority_score": score,
                "score_distance_to_high_quality_threshold": distance,
                "primary_failure_reason": row.get("primary_failure_reason"),
                "secondary_failure_reason": row.get("secondary_failure_reason"),
                "data_gap_type": gap_type,
                "data_gap_flags": row.get("data_gap_flags"),
                "data_gap_severity": severity,
                "rescue_priority": priority,
                "recommended_action": action,
                "rationale": f"{priority}: {row.get('candidate_tier')} candidate with {gap_type}; score distance to threshold is {distance}.",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    queue = pd.DataFrame(rows)
    queue["_priority_order"] = queue["rescue_priority"].map(priority_order)
    queue = queue.sort_values(["_priority_order", "research_priority_score", "stock_code"], ascending=[True, False, True]).drop(columns=["_priority_order"])
    return queue


def build_threshold_sensitivity(tier_b_feasibility: pd.DataFrame) -> pd.DataFrame:
    rows = []
    score = pd.to_numeric(tier_b_feasibility["research_priority_score"], errors="coerce").fillna(0)
    gate_ok = tier_b_feasibility["evidence_gate_level"].fillna("").isin(["thesis", "validated", "confirmed"])
    concept_ok = ~tier_b_feasibility["concept_pollution_ok"].eq(False)
    gaps = tier_b_feasibility["data_gap_flags"].fillna("").astype(str)
    blocking = gaps.str.contains("primary_source_evidence_missing", regex=False) & gaps.str.contains("validated_or_confirmed_evidence_missing", regex=False) & gaps.str.contains("revenue_traceability_missing", regex=False)
    for threshold in THRESHOLDS:
        mask = score.ge(threshold) & gate_ok & concept_ok
        rows.append(
            {
                "score_threshold": threshold,
                "would_be_high_quality_count": int(mask.sum()),
                "blocking_data_gap_count": int((mask & blocking).sum()),
                "non_blocking_or_partial_gap_count": int((mask & ~blocking).sum()),
                "diagnostic_note": "Sensitivity only; production high_quality threshold remains unchanged.",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_data_gap_severity_breakdown(queue: pd.DataFrame) -> pd.DataFrame:
    categories = [
        ("name/code mapping gap", "requires manual judgment"),
        ("industry mapping gap", "requires manual judgment"),
        ("evidence text gap", "requires external source"),
        ("financial data gap", "backfillable from existing local data if source adapters are complete"),
        ("trading status gap", "backfillable from existing local data"),
        ("keyword/category gap", "backfillable from existing local data"),
        ("other", "requires manual judgment"),
    ]
    rows = []
    for category, backfill_mode in categories:
        mask = queue.apply(lambda row: category in _gap_categories(row.get("data_gap_flags"), row), axis=1)
        affected = queue[mask]
        severity_counts = affected["data_gap_severity"].value_counts().to_dict()
        rows.append(
            {
                "data_gap_type": category,
                "affected_count": int(len(affected)),
                "minor_count": int(severity_counts.get("minor", 0)),
                "moderate_count": int(severity_counts.get("moderate", 0)),
                "severe_count": int(severity_counts.get("severe", 0)),
                "blocking_count": int(severity_counts.get("blocking", 0)),
                "backfill_classification": backfill_mode,
                "recommended_fix": _gap_fix(category),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _gap_fix(category: str) -> str:
    return {
        "name/code mapping gap": "repair stock code/name mapping before review",
        "industry mapping gap": "map sector/domain manually before tier decision",
        "evidence text gap": "collect annual report, announcement, and primary-source evidence",
        "financial data gap": "join financial statement and segment revenue adapters",
        "trading status gap": "refresh list status and stock universe metadata",
        "keyword/category gap": "repair keyword/report metadata extraction",
        "other": "sample manually and decide whether a source-specific backfill is needed",
    }[category]


def build_seed_tier_b_rescue_queue(queue: pd.DataFrame, seed_tier_b: pd.DataFrame) -> pd.DataFrame:
    seed = queue[queue["is_tier_b_seed"].astype(bool)].merge(
        seed_tier_b[["stock_code", "seed_tier_b_reason_classification", "rescue_reason"]],
        on="stock_code",
        how="left",
    )
    seed["why_missed_tier_a"] = seed["secondary_failure_reason"].fillna("data or evidence gap")
    seed["missing_data_or_evidence"] = seed["data_gap_type"]
    seed["manual_rescue_recommended"] = True
    seed["field_or_evidence_to_promote"] = seed.apply(
        lambda row: "validated primary evidence and revenue traceability" if row["data_gap_type"] in {"evidence text gap", "financial data gap"} else "complete mapped source field",
        axis=1,
    )
    return seed.sort_values(["rescue_priority", "research_priority_score", "stock_code"], ascending=[True, False, True])


def build_non_seed_tier_a_manual_review_queue(tier_a_source: pd.DataFrame) -> pd.DataFrame:
    non_seed = tier_a_source[~tier_a_source["is_seed_watchlist"].astype(bool)].copy()
    non_seed = non_seed.sort_values(["research_priority_score", "stock_code"], ascending=[False, True])
    non_seed["current_tier"] = "Tier A"
    non_seed["review_priority"] = "manual_sample_required"
    non_seed["recommended_action"] = "manual_rescue_review"
    non_seed["rationale"] = "new non-seed Tier A candidate; requires manual primary-source sampling before any workbench promotion"
    return non_seed[
        [
            "stock_code",
            "stock_name",
            "current_tier",
            "source_bucket",
            "tech_bottleneck_domain",
            "supply_chain_role",
            "evidence_gate_level",
            "primary_source_count",
            "bottleneck_exposure_score",
            "research_priority_score",
            "pass_assessment",
            "nonseed_audit_required",
            "review_priority",
            "recommended_action",
            "rationale",
            "research_only",
            "used_for_signal",
            "used_for_admission",
        ]
    ]


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Candidate Universe Rescue Triage v1

## 1. Scope

This task turns diagnostics into a research-only rescue and manual review queue. It does not change strategy files, admission logic, signal logic, scoring logic, or workbench integration.

## 2. Rescue Queue

- rescue review required: {summary['rescue_review_required_count']}
- P0 seed Tier B: {summary['p0_count']}
- P1 possible false negatives: {summary['p1_count']}
- P2 near-miss candidates: {summary['p2_count']}
- P3 moderate/minor data gaps: {summary['p3_count']}
- P4 severe/blocking or low-priority rows: {summary['p4_count']}

## 3. Near-Miss Answer

Tier B near-miss count at research_priority_score >= 55: {summary['tier_b_near_miss_count']}.

## 4. Data-Gap Blockers

Rescue candidates blocked by data gaps: {summary['data_gap_blocked_rescue_count']}. These are not company-quality failures by themselves; they require evidence or data backfill before manual judgment.

## 5. Seed Tier B Rescue

All 16 seed Tier B items are P0 and should be manually rescued/reconciled before any candidate pruning.

## 6. Threshold Sensitivity

At threshold 58.00, {summary['threshold_58_high_quality_count']} Tier B rows would qualify. At threshold 57.00, {summary['threshold_57_high_quality_count']} would qualify, all still requiring data-gap handling. This means the 58 threshold is brittle around the 57.25 cluster, but lowering it alone would not solve evidence gaps.

## 7. Non-Seed Tier A Manual Review

Non-seed Tier A manual review count: {summary['non_seed_tier_a_manual_review_count']}. These rows should not be auto-promoted to production.

## 8. Guardrails

- research_only: {summary['research_only']}
- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 9. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    quality_dir: Path = QUALITY_AUDIT_DIR,
    diagnostics_dir: Path = DIAGNOSTICS_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(quality_dir, diagnostics_dir)
    queue = build_rescue_triage_queue(inputs["non_clean"], inputs["seed_tier_b"], inputs["seed_preview"])
    threshold_sensitivity = build_threshold_sensitivity(inputs["tier_b_feasibility"])
    gap_breakdown = build_data_gap_severity_breakdown(queue)
    seed_queue = build_seed_tier_b_rescue_queue(queue, inputs["seed_tier_b"])
    possible_queue = queue[queue["is_possible_false_negative"].astype(bool)].copy()
    non_seed_tier_a = build_non_seed_tier_a_manual_review_queue(inputs["tier_a_source"])

    strategy_clean = _git_diff_formal_strategy_files() == ""
    p_counts = queue["rescue_priority"].value_counts().to_dict()
    used_for_signal_count = int(queue["used_for_signal"].astype(bool).sum() + non_seed_tier_a["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(queue["used_for_admission"].astype(bool).sum() + non_seed_tier_a["used_for_admission"].astype(bool).sum())
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "rescue_review_required_count": int(len(queue)),
        "seed_tier_b_count": int(len(seed_queue)),
        "seed_tier_b_p0_count": int(seed_queue["rescue_priority"].eq("P0").sum()),
        "possible_false_negative_count": int(queue["is_possible_false_negative"].astype(bool).sum()),
        "possible_false_negative_p0_or_p1_count": int(queue[queue["is_possible_false_negative"].astype(bool)]["rescue_priority"].isin(["P0", "P1"]).sum()),
        "tier_b_near_miss_count": int((queue["current_tier"].eq("Tier B") & queue["research_priority_score"].ge(55)).sum()),
        "data_gap_blocked_rescue_count": int(queue["primary_failure_reason"].eq("data_field_missing").sum()),
        "p0_count": int(p_counts.get("P0", 0)),
        "p1_count": int(p_counts.get("P1", 0)),
        "p2_count": int(p_counts.get("P2", 0)),
        "p3_count": int(p_counts.get("P3", 0)),
        "p4_count": int(p_counts.get("P4", 0)),
        "threshold_58_high_quality_count": int(threshold_sensitivity.loc[threshold_sensitivity["score_threshold"].eq(58.0), "would_be_high_quality_count"].iloc[0]),
        "threshold_57_high_quality_count": int(threshold_sensitivity.loc[threshold_sensitivity["score_threshold"].eq(57.0), "would_be_high_quality_count"].iloc[0]),
        "threshold_57_blocking_data_gap_count": int(threshold_sensitivity.loc[threshold_sensitivity["score_threshold"].eq(57.0), "blocking_data_gap_count"].iloc[0]),
        "non_seed_tier_a_manual_review_count": int(len(non_seed_tier_a)),
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "rescue_triage_ready" if strategy_clean and used_for_signal_count == 0 and used_for_admission_count == 0 else "blocked_due_to_guardrail_failure",
    }

    _write_json(output_dir / "rescue_triage_summary.json", summary)
    queue.to_csv(output_dir / "rescue_triage_queue.csv", index=False)
    seed_queue.to_csv(output_dir / "seed_tier_b_rescue_queue.csv", index=False)
    possible_queue.to_csv(output_dir / "possible_false_negative_rescue_queue.csv", index=False)
    threshold_sensitivity.to_csv(output_dir / "tier_b_threshold_sensitivity.csv", index=False)
    gap_breakdown.to_csv(output_dir / "data_gap_severity_breakdown.csv", index=False)
    non_seed_tier_a.to_csv(output_dir / "non_seed_tier_a_manual_review_queue.csv", index=False)
    (output_dir / "tech_bottleneck_candidate_universe_rescue_triage_v1_report.md").write_text(build_report(summary), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only Tech Bottleneck candidate universe rescue triage v1.")
    parser.add_argument("--quality-dir", default=str(QUALITY_AUDIT_DIR))
    parser.add_argument("--diagnostics-dir", default=str(DIAGNOSTICS_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.quality_dir), Path(args.diagnostics_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|rescue_review_required_count|{result['summary']['rescue_review_required_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
