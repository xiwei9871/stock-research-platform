#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRIAGE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

EXPECTED_NAMES = [
    "深圳能源",
    "德赛电池",
    "穗恒运Ａ",
    "顺发恒能",
    "万里扬",
    "圣阳股份",
    "道恩股份",
    "京泉华",
    "欣旺达",
    "易事特",
    "浙江力诺",
    "奕帆传动",
    "贵航股份",
    "德宏股份",
    "新中港",
    "神农集团",
]

RECONCILIATION_RULES: dict[str, dict[str, str]] = {
    "深圳能源": {
        "business_relevance_category": "energy_infrastructure_adjacent",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "keep in adjacent watchlist only; verify whether any power-electronics bottleneck exposure exists before reconsidering",
        "rationale": "Main exposure appears to be energy operation/infrastructure rather than a scarce hard-tech component, material, software, or equipment bottleneck.",
    },
    "德赛电池": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "backfill product revenue, BMS/pack exposure, named customer or certification evidence",
        "rationale": "Battery-pack/BMS style exposure can be a component lead, but current local evidence does not prove a bottleneck or chokepoint role.",
    },
    "穗恒运Ａ": {
        "business_relevance_category": "energy_infrastructure_adjacent",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "retain only as adjacent energy-infrastructure seed unless primary-source bottleneck evidence appears",
        "rationale": "Broad energy/power operation exposure is adjacent to the theme but not enough to establish a hard-tech bottleneck company.",
    },
    "顺发恒能": {
        "business_relevance_category": "energy_infrastructure_adjacent",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "check whether revenue is from operating assets versus scarce equipment/components",
        "rationale": "Current seed signal looks infrastructure-adjacent; data gap alone should not rescue it into a hard-tech candidate.",
    },
    "万里扬": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "verify transmission/storage component bottleneck evidence and revenue traceability",
        "rationale": "Component exposure may be relevant, but existing local evidence is not sufficient to treat it as a Tier A bottleneck candidate.",
    },
    "圣阳股份": {
        "business_relevance_category": "generic_new_energy",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "keep as generic new-energy adjacent unless product scarcity, certification, or revenue evidence proves bottleneck status",
        "rationale": "Battery/storage exposure is broadly related, but generic new-energy exposure is not automatically a bottleneck.",
    },
    "道恩股份": {
        "business_relevance_category": "key_material",
        "evidence_status": "insufficient",
        "reconciliation_decision": "true_rescue_to_tier_a_candidate",
        "recommended_next_action": "manually verify high-end material product, revenue exposure, customer validation, and substitution difficulty",
        "rationale": "Material exposure is closer to the hard-tech bottleneck method than energy-operation seeds, but still requires primary-source validation before any promotion.",
    },
    "京泉华": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "true_rescue_to_tier_a_candidate",
        "recommended_next_action": "verify magnetic component/power-electronics bottleneck evidence, customer certification, and revenue share",
        "rationale": "Power-electronics component exposure can plausibly map to a bottleneck candidate, but current local evidence is still incomplete.",
    },
    "欣旺达": {
        "business_relevance_category": "generic_new_energy",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "only retain as adjacent unless a scarce component/material or certification chokepoint is documented",
        "rationale": "Battery exposure is broad and may be important, but broad new-energy scale does not by itself prove a bottleneck role.",
    },
    "易事特": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "backfill UPS/power-electronics product evidence, segment revenue, and customer validation",
        "rationale": "Power infrastructure components may be relevant, but the local evidence package does not yet prove bottleneck economics.",
    },
    "浙江力诺": {
        "business_relevance_category": "industrial_software_or_equipment",
        "evidence_status": "insufficient",
        "reconciliation_decision": "true_rescue_to_tier_a_candidate",
        "recommended_next_action": "verify industrial control valve equipment positioning, certification cycle, and revenue traceability",
        "rationale": "Industrial equipment/control exposure is closer to a hard-tech bottleneck candidate and warrants manual rescue review.",
    },
    "奕帆传动": {
        "business_relevance_category": "key_component",
        "evidence_status": "missing",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "resolve company/product identity and collect transmission component primary-source evidence",
        "rationale": "The name suggests a component/drive-chain lead, but current local source support is too thin for classification beyond evidence backfill.",
    },
    "贵航股份": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "check aerospace/auto component product mix, military or aviation certification, and revenue contribution",
        "rationale": "Component exposure may be strategically relevant, but current energy-domain mapping looks suspect and requires source reconciliation.",
    },
    "德宏股份": {
        "business_relevance_category": "key_component",
        "evidence_status": "insufficient",
        "reconciliation_decision": "evidence_backfill_required",
        "recommended_next_action": "verify whether generator/electrical component products are scarce bottlenecks rather than generic auto parts",
        "rationale": "Potential component relevance exists, but current evidence does not establish a hard-tech bottleneck role.",
    },
    "新中港": {
        "business_relevance_category": "energy_infrastructure_adjacent",
        "evidence_status": "insufficient",
        "reconciliation_decision": "watchlist_only_adjacent",
        "recommended_next_action": "retain only as adjacent infrastructure unless scarce equipment or process evidence is found",
        "rationale": "Energy/thermal operation style exposure is adjacent, not a clear technology bottleneck.",
    },
    "神农集团": {
        "business_relevance_category": "unrelated_or_polluted",
        "evidence_status": "contradictory",
        "reconciliation_decision": "seed_pollution_remove_from_tech_bottleneck",
        "recommended_next_action": "remove from tech-bottleneck seed universe unless a new primary source proves a genuine hard-tech business line",
        "rationale": "The current semi/domain mapping conflicts with the apparent agriculture/livestock business identity; this is likely seed pollution.",
    },
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs(triage_dir: Path, quality_dir: Path) -> dict[str, Any]:
    return {
        "seed_queue": pd.read_csv(triage_dir / "seed_tier_b_rescue_queue.csv"),
        "triage_queue": pd.read_csv(triage_dir / "rescue_triage_queue.csv"),
        "triage_summary": json.loads((triage_dir / "rescue_triage_summary.json").read_text(encoding="utf-8")),
        "gap_severity": pd.read_csv(triage_dir / "data_gap_severity_breakdown.csv"),
        "seed_preview": pd.read_csv(quality_dir / "seed_watchlist_quality_preview.csv"),
        "tier_b_quality": pd.read_csv(quality_dir / "tier_b_quality_audit.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "gap_breakdown": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
    }


def _seed_reason(row: pd.Series, seed_preview: pd.DataFrame) -> str:
    preview = seed_preview[seed_preview["stock_code"].astype(str).eq(str(row["stock_code"]))]
    if preview.empty:
        return "seed reason unavailable in local outputs"
    hint = str(preview.iloc[0].get("reconciliation_hint", "") or "")
    status = str(preview.iloc[0].get("quality_status", "") or "")
    return f"seed quality preview: {status}; hint: {hint}"


def build_reconciliation(inputs: dict[str, Any]) -> pd.DataFrame:
    seed_queue = inputs["seed_queue"].copy()
    seed_preview = inputs["seed_preview"]
    actual_names = set(seed_queue["stock_name"].astype(str))
    expected_names = set(EXPECTED_NAMES)
    if actual_names != expected_names:
        raise ValueError(f"Unexpected seed Tier B names. missing={sorted(expected_names-actual_names)} extra={sorted(actual_names-expected_names)}")
    rows = []
    for _, row in seed_queue.sort_values("stock_code").iterrows():
        name = str(row["stock_name"])
        rule = RECONCILIATION_RULES[name]
        blocking = str(row.get("data_gap_flags", "") or row.get("missing_data_or_evidence", "") or "revenue_traceability_missing")
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": name,
                "current_tier": row.get("current_tier"),
                "research_priority_score": row.get("research_priority_score"),
                "data_gap_type": row.get("data_gap_type"),
                "blocking_field_or_evidence": blocking,
                "original_seed_reason": _seed_reason(row, seed_preview),
                "business_relevance_category": rule["business_relevance_category"],
                "evidence_status": rule["evidence_status"],
                "reconciliation_decision": rule["reconciliation_decision"],
                "recommended_next_action": rule["recommended_next_action"],
                "rationale": rule["rationale"],
                "auto_promote": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any], reconciliation: pd.DataFrame) -> str:
    true_rescue = ", ".join(reconciliation.loc[reconciliation["reconciliation_decision"].eq("true_rescue_to_tier_a_candidate"), "stock_name"].astype(str))
    adjacent = ", ".join(reconciliation.loc[reconciliation["reconciliation_decision"].eq("watchlist_only_adjacent"), "stock_name"].astype(str))
    pollution = ", ".join(reconciliation.loc[reconciliation["reconciliation_decision"].eq("seed_pollution_remove_from_tech_bottleneck"), "stock_name"].astype(str))
    backfill = ", ".join(reconciliation.loc[reconciliation["reconciliation_decision"].eq("evidence_backfill_required"), "stock_name"].astype(str))
    return f"""# Tech Bottleneck Candidate Universe Seed Tier B Reconciliation v1

## 1. Scope

This is a read-only reconciliation package for the 16 P0 seed Tier B candidates. It does not modify strategy files, admission logic, signal logic, scoring logic, or workbench integration.

## 2. Accounted Candidates

- candidate count: {summary['candidate_count']}
- expected seed names accounted for: {summary['expected_seed_names_accounted_for']}

## 3. Which Should Be Rescued

Manual Tier A rescue candidates: {true_rescue or 'none'}.

These are not auto-promoted. They should only enter manual source review.

## 4. Adjacent / Watchlist Only

Adjacent-only candidates: {adjacent or 'none'}.

## 5. Likely Seed Pollution

Seed pollution candidates: {pollution or 'none'}.

## 6. Evidence / Data Backfill Required

Evidence backfill required: {backfill or 'none'}.

## 7. Auto Promotion

Automatic promotion count: {summary['auto_promote_count']}. Expected answer: no candidate should be promoted automatically.

## 8. Guardrails

- research_only: {summary['research_only']}
- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 9. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    triage_dir: Path = TRIAGE_DIR,
    quality_dir: Path = QUALITY_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(triage_dir, quality_dir)
    reconciliation = build_reconciliation(inputs)
    strategy_clean = _git_diff_formal_strategy_files() == ""
    decision_counts = reconciliation["reconciliation_decision"].value_counts().to_dict()
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "candidate_count": int(len(reconciliation)),
        "expected_seed_names_accounted_for": set(reconciliation["stock_name"]) == set(EXPECTED_NAMES),
        "true_rescue_to_tier_a_candidate_count": int(decision_counts.get("true_rescue_to_tier_a_candidate", 0)),
        "watchlist_only_adjacent_count": int(decision_counts.get("watchlist_only_adjacent", 0)),
        "evidence_backfill_required_count": int(decision_counts.get("evidence_backfill_required", 0)),
        "data_backfill_required_count": int(decision_counts.get("data_backfill_required", 0)),
        "seed_pollution_remove_from_tech_bottleneck_count": int(decision_counts.get("seed_pollution_remove_from_tech_bottleneck", 0)),
        "unclear_manual_review_required_count": int(decision_counts.get("unclear_manual_review_required", 0)),
        "auto_promote_count": int(reconciliation["auto_promote"].astype(bool).sum()),
        "used_for_signal_count": int(reconciliation["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(reconciliation["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "seed_tier_b_reconciliation_ready" if strategy_clean else "blocked_due_to_guardrail_failure",
    }

    _write_json(output_dir / "seed_tier_b_reconciliation_summary.json", summary)
    reconciliation.to_csv(output_dir / "seed_tier_b_reconciliation.csv", index=False)
    reconciliation[reconciliation["reconciliation_decision"].eq("true_rescue_to_tier_a_candidate")].to_csv(output_dir / "seed_tier_b_true_rescue_candidates.csv", index=False)
    reconciliation[reconciliation["reconciliation_decision"].eq("watchlist_only_adjacent")].to_csv(output_dir / "seed_tier_b_watchlist_only_adjacent.csv", index=False)
    reconciliation[reconciliation["reconciliation_decision"].eq("seed_pollution_remove_from_tech_bottleneck")].to_csv(output_dir / "seed_tier_b_seed_pollution_candidates.csv", index=False)
    reconciliation[reconciliation["reconciliation_decision"].eq("evidence_backfill_required")].to_csv(output_dir / "seed_tier_b_evidence_backfill_required.csv", index=False)
    (output_dir / "tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1_report.md").write_text(build_report(summary, reconciliation), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only seed Tier B reconciliation package.")
    parser.add_argument("--triage-dir", default=str(TRIAGE_DIR))
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.triage_dir), Path(args.quality_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|candidate_count|{result['summary']['candidate_count']}")
    print(f"{TASK_NAME}|auto_promote_count|{result['summary']['auto_promote_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
