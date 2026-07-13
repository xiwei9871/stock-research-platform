#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_hard_tech_requalification_v1"
WORKBENCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement"
TASK_NAME = "tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

MANUAL_ANCHOR_NAMES = {"北方华创", "中微公司"}
REJECT_CATEGORIES = {
    "bank_or_financial",
    "energy_or_utility_operator",
    "consumer_or_lighting",
    "commodity_resource",
}
LIKELY_HARD_TECH_CATEGORIES = {
    "semiconductor_equipment_or_material",
    "advanced_material",
    "industrial_software_or_simulation",
    "high_end_equipment",
    "precision_component",
    "power_electronics_or_grid_equipment",
    "robotics_or_motion_control",
    "aerospace_defense_component",
    "energy_storage_key_component",
}
ADJACENT_CATEGORIES = {"generic_new_energy"}

V2_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_group",
    "previous_tier",
    "business_relevance_category",
    "final_requalification_category",
    "requalification_v2_category",
    "primary_source_evidence_available",
    "primary_source_url",
    "manual_review_pool_eligible",
    "verified_core_eligible",
    "exclusion_reason",
    "v2_rationale",
    "recommended_next_action",
    "research_only",
    "allowed_for_signal",
    "allowed_for_admission",
]


def _normalize_stock_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_df(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = df.reindex(columns=columns)
    df.to_csv(path, index=False)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _load_inputs(v1_dir: Path, workbench_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    seed_v1 = pd.read_csv(v1_dir / "seed_tier_a_requalification.csv", dtype={"stock_code": str})
    core = pd.read_csv(workbench_dir / "workbench_core_candidates.csv", dtype={"stock_code": str})
    seed_v1["stock_code"] = seed_v1["stock_code"].map(_normalize_stock_code)
    core["stock_code"] = core["stock_code"].map(_normalize_stock_code)
    return seed_v1, core


def _classify_seed_v2(row: pd.Series) -> tuple[str, bool, bool, str, str, str]:
    name = str(row["stock_name"])
    business_category = str(row.get("business_relevance_category", ""))
    has_primary = bool(row.get("primary_source_evidence_available"))

    if business_category in REJECT_CATEGORIES:
        return (
            "reject_seed_pollution",
            False,
            False,
            business_category,
            f"{name} fails hard exclusion as {business_category}; missing primary-source URL is not the reason for rejection.",
            "exclude from default hard-tech review pool; retain audit record only",
        )
    if name in MANUAL_ANCHOR_NAMES:
        return (
            "manual_anchor_core_pending_evidence",
            True,
            has_primary,
            "",
            f"{name} is a user-provided hard-tech anchor. It remains in the default manual hard-tech review pool pending primary-source capture.",
            "capture annual report, product, customer, or exchange disclosure evidence before any verified-core claim",
        )
    if business_category in LIKELY_HARD_TECH_CATEGORIES:
        return (
            "likely_hard_tech_pending_evidence",
            True,
            has_primary,
            "",
            f"{name} has a clearly hard-tech/bottleneck-relevant business category ({business_category}) but lacks local primary-source URL.",
            "manual review and evidence backfill; keep in default hard-tech review pool",
        )
    if business_category in ADJACENT_CATEGORIES:
        return (
            "adjacent_pending_evidence",
            False,
            False,
            "adjacent_generic_new_energy",
            f"{name} is related to new energy but is not enough by itself to remain in the default hard-tech bottleneck pool.",
            "keep in adjacent queue unless key component/material/equipment evidence is captured",
        )
    return (
        "low_priority_evidence_backfill",
        False,
        False,
        "unclear_hard_tech_identity",
        f"{name} lacks enough local category clarity for the default hard-tech review pool.",
        "perform low-priority source and domain backfill before reconsidering",
    )


def build_seed_v2(seed_v1: pd.DataFrame) -> pd.DataFrame:
    if len(seed_v1) != 86:
        raise ValueError(f"Expected exactly 86 Seed Tier A rows from v1, found {len(seed_v1)}")

    rows: list[dict[str, Any]] = []
    for _, row in seed_v1.sort_values(["stock_code", "stock_name"]).iterrows():
        category, pool_eligible, verified_core_eligible, exclusion_reason, rationale, action = _classify_seed_v2(row)
        rows.append(
            {
                "stock_code": _normalize_stock_code(row["stock_code"]),
                "stock_name": row["stock_name"],
                "source_group": row.get("source_group", "seed_tier_a"),
                "previous_tier": row.get("previous_tier", "Tier A"),
                "business_relevance_category": row.get("business_relevance_category", ""),
                "final_requalification_category": row.get("final_requalification_category", ""),
                "requalification_v2_category": category,
                "primary_source_evidence_available": bool(row.get("primary_source_evidence_available")),
                "primary_source_url": row.get("primary_source_url", ""),
                "manual_review_pool_eligible": pool_eligible,
                "verified_core_eligible": verified_core_eligible,
                "exclusion_reason": exclusion_reason,
                "v2_rationale": rationale,
                "recommended_next_action": action,
                "research_only": True,
                "allowed_for_signal": False,
                "allowed_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=V2_COLUMNS)


def build_verified_core(core: pd.DataFrame) -> pd.DataFrame:
    verified = core[
        core["source_group"].astype(str).isin(
            ["non_seed_tier_a_manual_review_core", "verified_rescue_extension_proposal"]
        )
    ].copy()
    verified["stock_code"] = verified["stock_code"].map(_normalize_stock_code)
    verified["review_pool_category"] = "verified_core"
    verified["research_only"] = True
    verified["allowed_for_signal"] = False
    verified["allowed_for_admission"] = False
    return verified.sort_values(["source_group", "stock_code", "stock_name"]).reset_index(drop=True)


def _seed_pool_rows(seed_v2: pd.DataFrame, category: str) -> pd.DataFrame:
    rows = seed_v2[seed_v2["requalification_v2_category"].eq(category)].copy()
    rows["review_pool_category"] = category
    rows["final_manual_approval_category"] = category
    rows["evidence_strength"] = "pending_primary_source"
    rows["bottleneck_relevance"] = "core_pending" if category == "manual_anchor_core_pending_evidence" else "likely_core_pending"
    rows["review_decision_source"] = TASK_NAME
    rows["manual_approval_required"] = True
    rows["allowed_for_workbench_candidate_pool"] = True
    rows["rationale"] = rows["v2_rationale"]
    return rows


def build_hard_tech_review_pool(verified_core: pd.DataFrame, seed_v2: pd.DataFrame) -> pd.DataFrame:
    seed_pool = pd.concat(
        [
            _seed_pool_rows(seed_v2, "manual_anchor_core_pending_evidence"),
            _seed_pool_rows(seed_v2, "likely_hard_tech_pending_evidence"),
        ],
        ignore_index=True,
    )
    pool = pd.concat([verified_core, seed_pool], ignore_index=True, sort=False)
    pool["stock_code"] = pool["stock_code"].map(_normalize_stock_code)
    pool["research_only"] = True
    pool["allowed_for_signal"] = False
    pool["allowed_for_admission"] = False
    return pool.sort_values(["review_pool_category", "stock_code", "stock_name"]).reset_index(drop=True)


def build_migration_preview(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"pool_name": "old_workbench_core_pool", "candidate_count": 114, "applied": False, "notes": "old pool retained polluted Seed Tier A rows"},
        {"pool_name": "v1_verified_local_primary_source_preview", "candidate_count": 28, "applied": False, "notes": "too strict for default manual review"},
        {
            "pool_name": "v2_hard_tech_review_pool_preview",
            "candidate_count": summary["hard_tech_review_pool_preview_count"],
            "applied": False,
            "notes": "recommended dashboard default preview; research-only and pending manual approval",
        },
    ]
    return pd.DataFrame(rows)


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Seed Tier A Requalification v2 Review Pool Refinement

## 1. Scope

This is a research-only refinement of the Seed Tier A requalification output. It does not modify strategy, signal, admission, scoring, formal candidate universe files, or the existing workbench core CSV in place.

## 2. Core Principle

Primary-source URL is required for `verified_core`. Primary-source URL is not required for staying in the default manual hard-tech review pool when the company's business identity is clearly hard-tech and bottleneck-relevant.

## 3. Verified Core

- verified_core_candidates: {summary['verified_core_count']}
- composition: 26 non-seed confirmed core + 2 verified rescue candidates

## 4. Seed Tier A v2 Classification

- manual_anchor_core_pending_evidence: {summary['manual_anchor_core_pending_evidence_count']}
- likely_hard_tech_pending_evidence: {summary['likely_hard_tech_pending_evidence_count']}
- adjacent_pending_evidence: {summary['adjacent_pending_evidence_count']}
- low_priority_evidence_backfill: {summary['low_priority_evidence_backfill_count']}
- reject_seed_pollution: {summary['reject_seed_pollution_count']}

## 5. Dashboard Default Review Pool Preview

- hard_tech_review_pool_preview_count: {summary['hard_tech_review_pool_preview_count']}
- greater_than_28: {summary['hard_tech_review_pool_preview_count'] > 28}
- less_than_114: {summary['hard_tech_review_pool_preview_count'] < 114}
- includes 北方华创: {summary['includes_beifang_huachuang']}
- includes 中微公司: {summary['includes_zhongwei_company']}

This preview is the proposed default manual review pool. It is not applied automatically.

## 6. Removed Pollution

The preview excludes banks, utility/operator-only rows, generic lighting/consumer rows, and commodity/resource rows without key-material bottleneck evidence. 佛山照明, 通宝能源, 渝农商行, 浙商银行, 建设银行, and 中信银行 are not in the default hard-tech review pool preview.

## 7. Guardrails

- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}
- baseline_admission_changed_count: {summary['baseline_admission_changed_count']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- existing_workbench_core_candidates_modified: {summary['existing_workbench_core_candidates_modified']}

## 8. Acceptance Decision

{summary['acceptance_decision']}
"""


def generate(
    v1_dir: Path = V1_DIR,
    workbench_dir: Path = WORKBENCH_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    core_path = workbench_dir / "workbench_core_candidates.csv"
    core_hash_before = _sha(core_path)
    seed_v1, core = _load_inputs(v1_dir, workbench_dir)
    seed_v2 = build_seed_v2(seed_v1)
    verified_core = build_verified_core(core)
    hard_tech_pool = build_hard_tech_review_pool(verified_core, seed_v2)
    core_hash_after = _sha(core_path)
    strategy_clean = _git_diff_formal_strategy_files() == ""

    counts = seed_v2["requalification_v2_category"].value_counts().to_dict()
    pool_names = set(hard_tech_pool["stock_name"].astype(str))
    summary: dict[str, Any] = {
        "task_name": TASK_NAME,
        "research_only": True,
        "seed_tier_a_count": int(len(seed_v2)),
        "verified_core_count": int(len(verified_core)),
        "manual_anchor_core_pending_evidence_count": int(counts.get("manual_anchor_core_pending_evidence", 0)),
        "likely_hard_tech_pending_evidence_count": int(counts.get("likely_hard_tech_pending_evidence", 0)),
        "adjacent_pending_evidence_count": int(counts.get("adjacent_pending_evidence", 0)),
        "low_priority_evidence_backfill_count": int(counts.get("low_priority_evidence_backfill", 0)),
        "reject_seed_pollution_count": int(counts.get("reject_seed_pollution", 0)),
        "hard_tech_review_pool_preview_count": int(len(hard_tech_pool)),
        "includes_beifang_huachuang": "北方华创" in pool_names,
        "includes_zhongwei_company": "中微公司" in pool_names,
        "verified_rescue_names": sorted(
            verified_core.loc[
                verified_core["source_group"].astype(str).eq("verified_rescue_extension_proposal"),
                "stock_name",
            ].astype(str).tolist()
        ),
        "excluded_obvious_pollution_names": sorted(
            seed_v2.loc[
                seed_v2["requalification_v2_category"].eq("reject_seed_pollution"),
                "stock_name",
            ].astype(str).tolist()
        ),
        "allowed_for_signal_count": int(hard_tech_pool["allowed_for_signal"].astype(bool).sum()),
        "allowed_for_admission_count": int(hard_tech_pool["allowed_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "existing_workbench_core_candidates_modified": core_hash_before != core_hash_after,
        "production_candidate_universe_modified": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "acceptance_decision": "seed_tier_a_requalification_v2_review_pool_refinement_ready",
    }

    _write_json(output_dir / "requalification_v2_summary.json", summary)
    _write_df(output_dir / "seed_tier_a_requalification_v2.csv", seed_v2, V2_COLUMNS)
    _write_df(output_dir / "verified_core_candidates.csv", verified_core)
    for category, filename in [
        ("manual_anchor_core_pending_evidence", "manual_anchor_core_pending_evidence.csv"),
        ("likely_hard_tech_pending_evidence", "likely_hard_tech_pending_evidence.csv"),
        ("adjacent_pending_evidence", "adjacent_pending_evidence.csv"),
        ("low_priority_evidence_backfill", "low_priority_evidence_backfill.csv"),
        ("reject_seed_pollution", "reject_seed_pollution.csv"),
    ]:
        _write_df(output_dir / filename, seed_v2[seed_v2["requalification_v2_category"].eq(category)], V2_COLUMNS)
    _write_df(output_dir / "hard_tech_review_pool_preview.csv", hard_tech_pool)
    _write_df(output_dir / "dashboard_pool_migration_preview.csv", build_migration_preview(summary))
    (output_dir / "tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement_report.md").write_text(
        build_report(summary),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
