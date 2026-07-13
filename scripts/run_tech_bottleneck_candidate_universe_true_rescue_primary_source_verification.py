#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
TRIAGE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
EXPECTED_NAMES = {"道恩股份", "京泉华", "浙江力诺"}


PRIMARY_SOURCE_VERIFICATION = {
    "道恩股份": {
        "candidate_thesis": "High-end polymer materials may be a key material exposure.",
        "claimed_bottleneck_link": "Potential constrained/import-substitution material chain; needs proof beyond generic chemical materials.",
        "primary_source_title": "山东道恩高分子材料股份有限公司2024年半年度报告摘要",
        "primary_source_type": "annual report",
        "source_date": "2024-08-27",
        "source_location_or_url": "https://static.cninfo.com.cn/finalpage/2024-08-27/1220982386.PDF",
        "exact_supporting_excerpt": "弹性体、改性塑料、色母粒、可降解材料、共聚酯解决方案",
        "evidence_category": "key_material",
        "evidence_strength": "weak",
        "bottleneck_relevance": "unclear",
        "verification_decision": "evidence_insufficient",
        "rationale": "Primary source verifies polymer material product lines, but it does not prove constrained supply, import substitution, customer certification, or value-capture bottleneck status.",
    },
    "京泉华": {
        "candidate_thesis": "Magnetic components and power-electronics products may be key components in power, charging, energy-storage, and industrial automation chains.",
        "claimed_bottleneck_link": "Potential magnetic component/power-electronics component exposure.",
        "primary_source_title": "深圳市京泉华科技股份有限公司2025年半年度报告",
        "primary_source_type": "semiannual/quarterly report",
        "source_date": "2025-08-28",
        "source_location_or_url": "https://static.cninfo.com.cn/finalpage/2025-08-28/1224593913.PDF",
        "exact_supporting_excerpt": "磁性元器件、电源、特种变压器均披露为收入分产品",
        "evidence_category": "key_component",
        "evidence_strength": "moderate",
        "bottleneck_relevance": "core",
        "verification_decision": "verified_rescue_candidate",
        "rationale": "Primary source verifies substantial magnetic-component, power, and special-transformer product revenue; bottleneck proof still needs manual customer/certification and substitution checks before any clean-subset consideration.",
    },
    "浙江力诺": {
        "candidate_thesis": "Industrial control valves and positioners may be industrial equipment/core components in process-industry automation chains.",
        "claimed_bottleneck_link": "Potential industrial equipment and process-control component exposure.",
        "primary_source_title": "浙江力诺流体控制科技股份有限公司2024年年度报告摘要",
        "primary_source_type": "annual report",
        "source_date": "2025-04-21",
        "source_location_or_url": "https://static.cninfo.com.cn/finalpage/2025-04-21/1223144530.PDF",
        "exact_supporting_excerpt": "控制阀是流程工业自动化过程控制中的关键基础部件",
        "evidence_category": "industrial_equipment",
        "evidence_strength": "strong",
        "bottleneck_relevance": "core",
        "verification_decision": "verified_rescue_candidate",
        "rationale": "Primary source explicitly identifies control valves as key basic components and core devices in process-industry automation; still no automatic promotion without manual source review.",
    },
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs(reconciliation_dir: Path, quality_dir: Path, triage_dir: Path) -> dict[str, Any]:
    return {
        "true_rescue": pd.read_csv(reconciliation_dir / "seed_tier_b_true_rescue_candidates.csv"),
        "reconciliation": pd.read_csv(reconciliation_dir / "seed_tier_b_reconciliation.csv"),
        "reconciliation_summary": json.loads((reconciliation_dir / "seed_tier_b_reconciliation_summary.json").read_text(encoding="utf-8")),
        "tier_b_quality": pd.read_csv(quality_dir / "tier_b_quality_audit.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "gap_breakdown": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
        "seed_preview": pd.read_csv(quality_dir / "seed_watchlist_quality_preview.csv"),
    }


def build_evidence_matrix(inputs: dict[str, Any]) -> pd.DataFrame:
    true_rescue = inputs["true_rescue"].copy()
    actual_names = set(true_rescue["stock_name"].astype(str))
    if actual_names != EXPECTED_NAMES:
        raise ValueError(f"Unexpected true rescue names. missing={sorted(EXPECTED_NAMES-actual_names)} extra={sorted(actual_names-EXPECTED_NAMES)}")
    rows = []
    for _, row in true_rescue.sort_values("stock_code").iterrows():
        name = str(row["stock_name"])
        evidence = PRIMARY_SOURCE_VERIFICATION.get(name)
        if evidence is None:
            evidence = {
                "candidate_thesis": str(row.get("rationale", "")),
                "claimed_bottleneck_link": str(row.get("recommended_next_action", "")),
                "primary_source_title": "",
                "primary_source_type": "missing",
                "source_date": "",
                "source_location_or_url": "",
                "exact_supporting_excerpt": "",
                "evidence_category": "other",
                "evidence_strength": "missing",
                "bottleneck_relevance": "unclear",
                "verification_decision": "evidence_insufficient",
                "rationale": "No local or curated primary-source evidence is available; do not infer from seed status.",
            }
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": name,
                "candidate_thesis": evidence["candidate_thesis"],
                "claimed_bottleneck_link": evidence["claimed_bottleneck_link"],
                "primary_source_title": evidence["primary_source_title"],
                "primary_source_type": evidence["primary_source_type"],
                "source_date": evidence["source_date"],
                "source_location_or_url": evidence["source_location_or_url"],
                "exact_supporting_excerpt": evidence["exact_supporting_excerpt"],
                "evidence_category": evidence["evidence_category"],
                "evidence_strength": evidence["evidence_strength"],
                "bottleneck_relevance": evidence["bottleneck_relevance"],
                "verification_decision": evidence["verification_decision"],
                "rationale": evidence["rationale"],
                "future_clean_subset_consideration": evidence["verification_decision"] == "verified_rescue_candidate",
                "auto_promote": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _empty_like(matrix: pd.DataFrame) -> pd.DataFrame:
    return matrix.iloc[0:0].copy()


def build_report(summary: dict[str, Any], matrix: pd.DataFrame) -> str:
    verified = ", ".join(matrix.loc[matrix["verification_decision"].eq("verified_rescue_candidate"), "stock_name"].astype(str))
    adjacent = ", ".join(matrix.loc[matrix["verification_decision"].eq("downgrade_to_adjacent_watchlist"), "stock_name"].astype(str))
    insufficient = ", ".join(matrix.loc[matrix["verification_decision"].eq("evidence_insufficient"), "stock_name"].astype(str))
    rejected = ", ".join(matrix.loc[matrix["verification_decision"].eq("reject_seed_pollution"), "stock_name"].astype(str))
    return f"""# Tech Bottleneck True Rescue Primary Source Verification v1

## 1. Scope

This task verifies the three true-rescue candidates with primary-source evidence only. It is research-only and does not modify formal strategy files, admission logic, signal logic, scoring logic, or the production candidate universe.

## 2. Verified By Primary Source

Verified rescue candidates: {verified or 'none'}.

These may be considered for future manual clean-subset review, but they are not auto-promoted.

## 3. Adjacent Only

Downgrade to adjacent watchlist: {adjacent or 'none'}.

## 4. Evidence Insufficient

Evidence insufficient: {insufficient or 'none'}.

## 5. Rejected Despite Reconciliation Rescue

Rejected as seed pollution: {rejected or 'none'}.

## 6. Future Clean-Subset Consideration

Future consideration count: {summary['future_clean_subset_consideration_count']}. This only means primary-source evidence is strong enough for future manual review; it is not a production promotion.

## 7. Auto Promotion

Auto-promote count: {summary['auto_promote_count']}. Expected answer: none.

## 8. Guardrails

- research_only: {summary['research_only']}
- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 9. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    reconciliation_dir: Path = RECONCILIATION_DIR,
    quality_dir: Path = QUALITY_DIR,
    triage_dir: Path = TRIAGE_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(reconciliation_dir, quality_dir, triage_dir)
    matrix = build_evidence_matrix(inputs)
    strategy_clean = _git_diff_formal_strategy_files() == ""
    decision_counts = matrix["verification_decision"].value_counts().to_dict()
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "candidate_count": int(len(matrix)),
        "expected_candidates_accounted_for": set(matrix["stock_name"]) == EXPECTED_NAMES,
        "verified_rescue_candidate_count": int(decision_counts.get("verified_rescue_candidate", 0)),
        "evidence_insufficient_count": int(decision_counts.get("evidence_insufficient", 0)),
        "downgrade_to_adjacent_watchlist_count": int(decision_counts.get("downgrade_to_adjacent_watchlist", 0)),
        "reject_seed_pollution_count": int(decision_counts.get("reject_seed_pollution", 0)),
        "future_clean_subset_consideration_count": int(matrix["future_clean_subset_consideration"].astype(bool).sum()),
        "auto_promote_count": int(matrix["auto_promote"].astype(bool).sum()),
        "used_for_signal_count": int(matrix["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(matrix["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "true_rescue_primary_source_verification_ready" if strategy_clean else "blocked_due_to_guardrail_failure",
    }

    _write_json(output_dir / "true_rescue_primary_source_verification_summary.json", summary)
    matrix.to_csv(output_dir / "true_rescue_primary_source_evidence_matrix.csv", index=False)
    matrix[matrix["verification_decision"].eq("verified_rescue_candidate")].to_csv(output_dir / "verified_rescue_candidates.csv", index=False)
    matrix[matrix["verification_decision"].eq("evidence_insufficient")].to_csv(output_dir / "evidence_insufficient_rescue_candidates.csv", index=False)
    adjacent = matrix[matrix["verification_decision"].eq("downgrade_to_adjacent_watchlist")]
    (adjacent if not adjacent.empty else _empty_like(matrix)).to_csv(output_dir / "downgrade_to_adjacent_watchlist.csv", index=False)
    rejected = matrix[matrix["verification_decision"].eq("reject_seed_pollution")]
    (rejected if not rejected.empty else _empty_like(matrix)).to_csv(output_dir / "rejected_seed_pollution_candidates.csv", index=False)
    (output_dir / "tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1_report.md").write_text(build_report(summary, matrix), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only primary-source verification for true rescue candidates.")
    parser.add_argument("--reconciliation-dir", default=str(RECONCILIATION_DIR))
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--triage-dir", default=str(TRIAGE_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.reconciliation_dir), Path(args.quality_dir), Path(args.triage_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|candidate_count|{result['summary']['candidate_count']}")
    print(f"{TASK_NAME}|auto_promote_count|{result['summary']['auto_promote_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
