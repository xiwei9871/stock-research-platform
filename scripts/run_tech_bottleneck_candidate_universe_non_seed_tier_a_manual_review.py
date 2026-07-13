#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
DIAGNOSTICS_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
EXTENSION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

PASS_ASSESSMENT = "pass_by_construction_not_independent_validation"


CORE_NAMES = {
    "福晶科技",
    "光迅科技",
    "沪电股份",
    "中京电子",
    "洁美科技",
    "深南电路",
    "鹏鼎控股",
    "雷赛智能",
    "鼎龙股份",
    "上海新阳",
    "中际旭创",
    "三环集团",
    "光智科技",
    "新易盛",
    "精测电子",
    "长川科技",
    "珂玛科技",
    "生益科技",
    "有研新材",
    "江化微",
    "火炬电子",
    "泰晶科技",
    "格林达",
    "立昂微",
    "伟测科技",
    "裕太微",
}
ADJACENT_NAMES = {
    "冰轮环境",
    "智光电气",
    "电光科技",
    "旭光电子",
    "远东股份",
    "四方股份",
    "德业股份",
    "江苏北人",
}
BACKFILL_NAMES = {
    "激智科技",
    "鸿富瀚",
    "峰岹科技",
    "金橙子",
    "奕瑞科技",
    "华光新材",
}
DOWNGRADE_NAMES = {
    "金橙子",
    "奕瑞科技",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs(quality_dir: Path, diagnostics_dir: Path, extension_dir: Path) -> dict[str, Any]:
    return {
        "tier_a_quality": pd.read_csv(quality_dir / "tier_a_quality_audit.csv"),
        "clean_subset": pd.read_csv(quality_dir / "clean_candidate_subset.csv"),
        "seed_preview": pd.read_csv(quality_dir / "seed_watchlist_quality_preview.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "gap_breakdown": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
        "quality_summary": json.loads((quality_dir / "candidate_universe_quality_audit_summary.json").read_text(encoding="utf-8")),
        "quality_guardrails": json.loads((quality_dir / "candidate_universe_quality_audit_guardrails.json").read_text(encoding="utf-8")),
        "tier_a_source": pd.read_csv(diagnostics_dir / "tier_a_seed_vs_nonseed_audit.csv"),
        "diagnostics_summary": json.loads((diagnostics_dir / "audit_diagnostics_summary.json").read_text(encoding="utf-8")),
        "extension_summary": json.loads((extension_dir / "clean_subset_extension_proposal_summary.json").read_text(encoding="utf-8")),
        "extension_proposed": pd.read_csv(extension_dir / "proposed_clean_subset_additions.csv"),
        "extension_not_proposed": pd.read_csv(extension_dir / "not_proposed_rescue_candidates.csv"),
        "extension_guardrails": json.loads((extension_dir / "clean_subset_extension_guardrails.json").read_text(encoding="utf-8")),
    }


def _business_category(row: pd.Series) -> str:
    name = str(row.get("stock_name", ""))
    domain = str(row.get("tech_bottleneck_domain", ""))
    if name in {"生益科技", "沪电股份", "中京电子", "深南电路", "鹏鼎控股", "三环集团", "火炬电子", "泰晶科技"}:
        return "key_material" if name in {"生益科技", "中京电子", "沪电股份"} else "key_component"
    if domain == "半导体":
        return "key_material" if name in {"鼎龙股份", "上海新阳", "江化微", "格林达", "有研新材"} else "core_tech_bottleneck"
    if domain == "光电与通信":
        return "key_component"
    if domain == "高端仪器仪表与科学仪器":
        return "industrial_equipment"
    if domain == "工业软件与基础软件":
        return "industrial_software"
    if domain == "航空航天与军工电子":
        return "supply_chain_security"
    if domain == "能源与电力电子关键环节":
        return "adjacent_industry"
    if name in BACKFILL_NAMES:
        return "unclear"
    return "core_tech_bottleneck" if name in CORE_NAMES else "unclear"


def _decision(row: pd.Series) -> tuple[str, str, str, str, str]:
    name = str(row.get("stock_name", ""))
    category = _business_category(row)
    source_count = int(row.get("primary_source_count", 0) or 0)
    gate = str(row.get("evidence_gate_level", ""))
    if name in DOWNGRADE_NAMES:
        return (
            category,
            "moderate",
            "unclear",
            "downgrade_manual_review_required",
            "domain mapping is plausible but not enough to treat as core without primary-source thesis review",
        )
    if name in BACKFILL_NAMES:
        return (
            category,
            "moderate" if source_count >= 5 else "insufficient",
            "unclear",
            "evidence_backfill_required",
            "collect product-specific primary-source evidence and clarify bottleneck role before promotion",
        )
    if name in ADJACENT_NAMES:
        return (
            category,
            "moderate",
            "adjacent",
            "confirm_adjacent_watchlist",
            "relevant industrial or energy-adjacent exposure, but current mapping should stay watchlist/manual-review only",
        )
    if name in CORE_NAMES and gate in {"confirmed", "validated"} and source_count >= 5:
        return (
            category,
            "sufficient" if gate == "confirmed" else "moderate",
            "core",
            "confirm_core_candidate",
            "non-seed Tier A has confirmed/validated source support and a plausible hard-tech bottleneck category",
        )
    return (
        "unclear",
        "insufficient",
        "unclear",
        "evidence_backfill_required",
        "Tier A pass is not independent proof; source-level bottleneck evidence remains incomplete",
    )


def build_review(inputs: dict[str, Any]) -> pd.DataFrame:
    source = inputs["tier_a_source"]
    non_seed = source[~source["is_seed_watchlist"].astype(bool)].copy()
    if len(non_seed) != 40:
        raise ValueError(f"Expected 40 non-seed Tier A candidates, found {len(non_seed)}")
    rows = []
    for _, row in non_seed.sort_values("stock_code").iterrows():
        category, evidence, relevance, decision, action_note = _decision(row)
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "is_seed_watchlist": False,
                "current_tier": "Tier A",
                "research_priority_score": row.get("research_priority_score"),
                "tier_a_pass_reason": row.get("pass_assessment") or PASS_ASSESSMENT,
                "business_relevance_category": category,
                "evidence_status": evidence,
                "bottleneck_relevance": relevance,
                "review_decision": decision,
                "recommended_next_action": action_note,
                "rationale": f"{action_note}. Manual approval remains required because Tier A pass is pass-by-construction.",
                "manual_approval_required": True,
                "auto_promote": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Non-Seed Tier A Manual Review v1

## 1. Scope

This is a research-only review package for non-seed Tier A candidates. It does not modify formal strategy files, admission logic, signal logic, scoring logic, workbench integration, or the existing clean_candidate_subset.csv.

## 2. Tier A Pass Caveat

Tier A pass is explicitly treated as `{PASS_ASSESSMENT}`. This package is an independent quality check before any workbench patch.

## 3. Review Summary

- total non-seed Tier A reviewed: {summary['total_non_seed_tier_a_reviewed']}
- confirm core candidate: {summary['confirm_core_candidate_count']}
- adjacent/watchlist: {summary['confirm_adjacent_watchlist_count']}
- evidence backfill required: {summary['evidence_backfill_required_count']}
- downgrade/manual review required: {summary['downgrade_manual_review_required_count']}
- likely false positive: {summary['likely_false_positive_count']}
- manual approval required: {summary['manual_approval_required_count']}

## 4. Extension Proposal Context

- current clean subset count: {summary['current_clean_subset_count']}
- proposed extension count: {summary['proposed_extension_count']}
- proposed clean subset count: {summary['proposed_clean_subset_count']}
- extension applied: {summary['extension_applied']}

The two rescue additions remain proposal-only and have not been applied.

## 5. Guardrails

- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 6. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    quality_dir: Path = QUALITY_DIR,
    diagnostics_dir: Path = DIAGNOSTICS_DIR,
    extension_dir: Path = EXTENSION_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(quality_dir, diagnostics_dir, extension_dir)
    review = build_review(inputs)
    decision_counts = review["review_decision"].value_counts().to_dict()
    extension = inputs["extension_summary"]
    strategy_clean = _git_diff_formal_strategy_files() == ""
    used_for_signal_count = int(review["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(review["used_for_admission"].astype(bool).sum())
    auto_promote_count = int(review["auto_promote"].astype(bool).sum())
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "total_non_seed_tier_a_reviewed": int(len(review)),
        "confirm_core_candidate_count": int(decision_counts.get("confirm_core_candidate", 0)),
        "confirm_adjacent_watchlist_count": int(decision_counts.get("confirm_adjacent_watchlist", 0)),
        "evidence_backfill_required_count": int(decision_counts.get("evidence_backfill_required", 0)),
        "downgrade_manual_review_required_count": int(decision_counts.get("downgrade_manual_review_required", 0)),
        "likely_false_positive_count": int(decision_counts.get("likely_false_positive", 0)),
        "manual_approval_required_count": int(review["manual_approval_required"].astype(bool).sum()),
        "tier_a_pass_assessment": PASS_ASSESSMENT,
        "current_clean_subset_count": int(extension.get("current_clean_subset_count", 126)),
        "proposed_extension_count": int(extension.get("proposed_addition_count", 2)),
        "proposed_clean_subset_count": int(extension.get("proposed_clean_subset_count", 128)),
        "extension_applied": False,
        "auto_promote_count": auto_promote_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "non_seed_tier_a_manual_review_ready" if strategy_clean and auto_promote_count == 0 else "blocked_due_to_guardrail_failure",
    }
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "clean_candidate_subset_modified_in_place": False,
        "workbench_integration_modified": False,
        "auto_promote_count": auto_promote_count,
        "manual_approval_required_count": summary["manual_approval_required_count"],
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": summary["acceptance_decision"],
    }

    _write_json(output_dir / "non_seed_tier_a_manual_review_summary.json", summary)
    review.to_csv(output_dir / "non_seed_tier_a_manual_review.csv", index=False)
    review[review["review_decision"].eq("confirm_core_candidate")].to_csv(output_dir / "non_seed_tier_a_confirm_core_candidates.csv", index=False)
    review[review["review_decision"].eq("confirm_adjacent_watchlist")].to_csv(output_dir / "non_seed_tier_a_adjacent_watchlist.csv", index=False)
    review[review["review_decision"].eq("evidence_backfill_required")].to_csv(output_dir / "non_seed_tier_a_evidence_backfill_required.csv", index=False)
    review[review["review_decision"].eq("likely_false_positive")].to_csv(output_dir / "non_seed_tier_a_likely_false_positive.csv", index=False)
    _write_json(output_dir / "non_seed_tier_a_review_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1_report.md").write_text(build_report(summary), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only non-seed Tier A manual review package.")
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--diagnostics-dir", default=str(DIAGNOSTICS_DIR))
    parser.add_argument("--extension-dir", default=str(EXTENSION_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.quality_dir), Path(args.diagnostics_dir), Path(args.extension_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|total_non_seed_tier_a_reviewed|{result['summary']['total_non_seed_tier_a_reviewed']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
