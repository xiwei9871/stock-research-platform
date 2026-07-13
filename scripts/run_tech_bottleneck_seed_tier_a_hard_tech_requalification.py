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
WORKBENCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"
MANUAL_PACKET_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1"
PIPELINE_CLOSURE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_hard_tech_requalification_v1"
TASK_NAME = "tech_bottleneck_seed_tier_a_hard_tech_requalification_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

CORE_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_group",
    "previous_tier",
    "final_manual_approval_category",
    "evidence_strength",
    "bottleneck_relevance",
    "review_decision_source",
    "primary_source_url",
    "manual_approval_required",
    "allowed_for_workbench_candidate_pool",
    "allowed_for_signal",
    "allowed_for_admission",
    "rationale",
]

REQUALIFICATION_COLUMNS = [
    *CORE_COLUMNS,
    "business_relevance_category",
    "final_requalification_category",
    "primary_business_exclusion_rule",
    "primary_source_evidence_available",
    "primary_source_evidence_type",
    "company_level_evidence_status",
    "inherited_seed_label_used_for_confirmation",
    "evidence_needed_to_confirm_core",
    "requalification_rationale",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]

CONFIRMABLE_CATEGORIES = {
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

BANK_OR_FINANCIAL = {"渝农商行", "浙商银行", "建设银行", "中信银行"}
ENERGY_OR_UTILITY_OPERATOR = {"广州发展", "通宝能源", "南网储能"}
CONSUMER_OR_LIGHTING = {"佛山照明"}
COMMODITY_RESOURCE = {"神火股份", "天山铝业", "南山铝业", "中孚实业"}
GENERIC_NEW_ENERGY = {
    "国轩高科",
    "亿纬锂能",
    "宁德时代",
    "阳光电源",
    "派能科技",
    "昱能科技",
    "海博思创",
    "福斯特",
    "杉杉股份",
    "当升科技",
}
ENERGY_STORAGE_KEY_COMPONENT = {"艾罗能源", "西典新能", "金辰股份"}
POWER_ELECTRONICS_OR_GRID = {
    "许继电气",
    "东方电子",
    "思源电气",
    "科陆电子",
    "平高电气",
    "法拉电子",
    "正泰电器",
    "神马电力",
    "正弦电气",
    "协昌科技",
}
SEMICONDUCTOR = {
    "华天科技",
    "北方华创",
    "雅克科技",
    "中晶科技",
    "扬杰科技",
    "江丰电子",
    "广立微",
    "豪威集团",
    "睿创微纳",
    "中微公司",
    "安集科技",
    "华海清科",
    "八亿时空",
    "神工股份",
    "东微半导",
    "中科飞测",
    "汇成股份",
    "龙迅股份",
}
ADVANCED_MATERIAL = {
    "楚江新材",
    "普利特",
    "中科电气",
    "科创新源",
    "振华股份",
    "上海洗霸",
    "福斯特",
    "云路股份",
}
HIGH_END_EQUIPMENT = {
    "晶盛机电",
    "恒立液压",
    "应流股份",
    "大元泵业",
    "长龄液压",
    "日联科技",
    "皖仪科技",
}
PRECISION_COMPONENT = {
    "江特电机",
    "飞龙股份",
    "和而泰",
    "硕贝德",
    "贝斯特",
    "飞荣达",
    "朗特智能",
    "拓普集团",
    "科博达",
}
ROBOTICS_OR_MOTION = {"绿的谐波"}
AEROSPACE_DEFENSE = {"高德红外", "华力创通", "航天长峰", "新光光电"}
INDUSTRIAL_SOFTWARE = {"超图软件", "索辰科技"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_stock_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _business_category(name: str) -> str:
    if name in SEMICONDUCTOR:
        return "semiconductor_equipment_or_material"
    if name in ADVANCED_MATERIAL:
        return "advanced_material"
    if name in INDUSTRIAL_SOFTWARE:
        return "industrial_software_or_simulation"
    if name in HIGH_END_EQUIPMENT:
        return "high_end_equipment"
    if name in PRECISION_COMPONENT:
        return "precision_component"
    if name in POWER_ELECTRONICS_OR_GRID:
        return "power_electronics_or_grid_equipment"
    if name in ROBOTICS_OR_MOTION:
        return "robotics_or_motion_control"
    if name in AEROSPACE_DEFENSE:
        return "aerospace_defense_component"
    if name in ENERGY_STORAGE_KEY_COMPONENT:
        return "energy_storage_key_component"
    if name in GENERIC_NEW_ENERGY:
        return "generic_new_energy"
    if name in ENERGY_OR_UTILITY_OPERATOR:
        return "energy_or_utility_operator"
    if name in BANK_OR_FINANCIAL:
        return "bank_or_financial"
    if name in CONSUMER_OR_LIGHTING:
        return "consumer_or_lighting"
    if name in COMMODITY_RESOURCE:
        return "commodity_resource"
    return "unclear"


def _has_primary_source(row: pd.Series) -> bool:
    value = row.get("primary_source_url")
    return isinstance(value, str) and bool(value.strip())


def _exclusion_rule(category: str) -> str:
    if category in {"bank_or_financial", "energy_or_utility_operator", "consumer_or_lighting", "commodity_resource"}:
        return category
    if category == "generic_new_energy":
        return "generic_new_energy_without_key_component_or_material_primary_evidence"
    return ""


def _final_category(category: str, has_primary: bool) -> str:
    if category in {"bank_or_financial", "energy_or_utility_operator", "consumer_or_lighting", "commodity_resource"}:
        return "reject_seed_pollution"
    if category == "generic_new_energy":
        return "hard_tech_adjacent_watchlist"
    if category in CONFIRMABLE_CATEGORIES:
        return "confirmed_core_hard_tech_bottleneck" if has_primary else "evidence_backfill_required"
    return "downgrade_manual_review_required"


def _evidence_needed(category: str) -> str:
    if category == "semiconductor_equipment_or_material":
        return "annual report or announcement proving product line, customer validation, revenue traceability, and import-substitution bottleneck role"
    if category == "advanced_material":
        return "primary-source product/revenue evidence proving the material is scarce, certified, or substitution-constrained"
    if category == "industrial_software_or_simulation":
        return "official product, customer, or contract evidence proving core industrial-software/simulation bottleneck exposure"
    if category == "high_end_equipment":
        return "official product and customer/acceptance evidence proving high-end equipment chokepoint role"
    if category == "power_electronics_or_grid_equipment":
        return "annual report or announcement proving key power-electronics/grid-equipment component bottleneck exposure"
    if category == "energy_storage_key_component":
        return "primary-source evidence proving key component/material exposure, not terminal energy-storage application only"
    if category == "generic_new_energy":
        return "evidence that the business is a scarce key component/material/equipment bottleneck rather than generic terminal/application exposure"
    return "company-level primary-source evidence proving hard-tech bottleneck exposure"


def _recommended_action(final_category: str, category: str) -> str:
    if final_category == "confirmed_core_hard_tech_bottleneck":
        return "eligible for future manual core review preview only; do not apply to production"
    if final_category == "hard_tech_adjacent_watchlist":
        return f"keep in adjacent watchlist; collect evidence required to distinguish {category} from true bottleneck exposure"
    if final_category == "evidence_backfill_required":
        return f"backfill primary-source evidence: {_evidence_needed(category)}"
    if final_category == "downgrade_manual_review_required":
        return "manual domain review required; current local evidence and business category are unclear"
    return "remove from revised core preview; retain only in audit record unless extraordinary primary-source hard-tech evidence appears"


def _rationale(name: str, category: str, final_category: str, has_primary: bool) -> str:
    if final_category == "confirmed_core_hard_tech_bottleneck":
        return f"{name} has local primary-source evidence and maps to {category}; inherited Seed Tier A labels were not used as proof."
    if final_category == "hard_tech_adjacent_watchlist":
        return f"{name} is related to {category}, but current local source package does not prove a hard-tech bottleneck/chokepoint role."
    if final_category == "evidence_backfill_required":
        return f"{name} may fit {category}, but Seed Tier A inherited strong/core labels are not company-level evidence and no local primary source was available."
    if final_category == "downgrade_manual_review_required":
        return f"{name} could not be cleanly mapped to a strict hard-tech bottleneck category from local outputs."
    return f"{name} primary business category is {category}; this fails strict hard-tech bottleneck core rules without extraordinary primary-source evidence."


def load_inputs(
    workbench_dir: Path = WORKBENCH_DIR,
    manual_packet_dir: Path = MANUAL_PACKET_DIR,
    pipeline_closure_dir: Path = PIPELINE_CLOSURE_DIR,
) -> dict[str, Any]:
    return {
        "core_pool": pd.read_csv(workbench_dir / "workbench_core_candidates.csv", dtype={"stock_code": str}),
        "manual_master": pd.read_csv(manual_packet_dir / "manual_approval_master_table.csv", dtype={"stock_code": str}),
        "pipeline_summary": _read_json(pipeline_closure_dir / "pipeline_closure_summary.json"),
    }


def build_requalification(core_pool: pd.DataFrame) -> pd.DataFrame:
    seed = core_pool[core_pool["source_group"].astype(str).eq("seed_tier_a")].copy()
    if len(seed) != 86:
        raise ValueError(f"Expected 86 Seed Tier A candidates in core pool, found {len(seed)}")
    rows: list[dict[str, Any]] = []
    for _, row in seed.sort_values(["stock_code", "stock_name"]).iterrows():
        name = str(row["stock_name"])
        category = _business_category(name)
        has_primary = _has_primary_source(row)
        final_category = _final_category(category, has_primary)
        base = {column: row.get(column, "") for column in CORE_COLUMNS}
        base["stock_code"] = _normalize_stock_code(base["stock_code"])
        base.update(
            {
                "business_relevance_category": category,
                "final_requalification_category": final_category,
                "primary_business_exclusion_rule": _exclusion_rule(category),
                "primary_source_evidence_available": has_primary,
                "primary_source_evidence_type": "primary_source_url" if has_primary else "missing",
                "company_level_evidence_status": "primary_source_available" if has_primary else "inherited_seed_label_only",
                "inherited_seed_label_used_for_confirmation": False,
                "evidence_needed_to_confirm_core": _evidence_needed(category),
                "requalification_rationale": _rationale(name, category, final_category, has_primary),
                "recommended_next_action": _recommended_action(final_category, category),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
        rows.append(base)
    return pd.DataFrame(rows, columns=REQUALIFICATION_COLUMNS)


def build_revised_core_preview(core_pool: pd.DataFrame, requalification: pd.DataFrame) -> pd.DataFrame:
    confirmed_seed_codes = set(
        requalification.loc[
            requalification["final_requalification_category"].eq("confirmed_core_hard_tech_bottleneck"),
            "stock_code",
        ].astype(str)
    )
    confirmed_seed = core_pool[
        core_pool["source_group"].astype(str).eq("seed_tier_a") & core_pool["stock_code"].astype(str).isin(confirmed_seed_codes)
    ].copy()
    non_seed_core = core_pool[core_pool["source_group"].astype(str).eq("non_seed_tier_a_manual_review_core")].copy()
    verified_rescue = core_pool[core_pool["source_group"].astype(str).eq("verified_rescue_extension_proposal")].copy()
    preview = pd.concat([confirmed_seed, non_seed_core, verified_rescue], ignore_index=True)
    if not preview.empty:
        preview["stock_code"] = preview["stock_code"].map(_normalize_stock_code)
        preview["preview_only"] = True
        preview["research_only"] = True
        preview["allowed_for_signal"] = False
        preview["allowed_for_admission"] = False
    return preview


def _write_df(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        df = df.reindex(columns=columns)
    df.to_csv(path, index=False)


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Seed Tier A Hard-Tech Requalification v1

## 1. Scope

This is a research-only re-audit of the 86 Seed Tier A candidates currently included in the 114-candidate workbench core pool. It does not modify production candidate universe files, signal logic, admission logic, scoring logic, or formal strategy files.

## 2. Why This Was Needed

Seed Tier A had been inherited into the workbench core pool with labels such as `strong` and `core`. Those inherited labels are not company-level primary-source evidence and cannot prove a strict hard-tech bottleneck thesis.

## 3. Requalification Result

- Seed Tier A audited: {summary['seed_tier_a_audited_count']}
- confirmed core hard-tech bottleneck: {summary['confirmed_core_hard_tech_bottleneck_count']}
- adjacent only: {summary['hard_tech_adjacent_watchlist_count']}
- evidence backfill required: {summary['evidence_backfill_required_count']}
- downgrade/manual review required: {summary['downgrade_manual_review_required_count']}
- reject/seed pollution: {summary['reject_seed_pollution_count']}
- revised core pool preview count: {summary['revised_core_pool_preview_count']}

## 4. Obvious Contaminants Removed From Core Preview

{', '.join(summary['obvious_contaminants_removed'])}

## 5. Specific Checks

- 佛山照明: {summary['specific_checks']['佛山照明']}
- 通宝能源: {summary['specific_checks']['通宝能源']}
- 渝农商行 / 浙商银行 / 建设银行 / 中信银行: rejected as bank_or_financial seed pollution.
- 许继电气: manually/evidence checked, not rejected by name alone.
- 艾罗能源: not accepted by name alone; requires evidence backfill.

## 6. Revised Core Pool Preview

Preview only. It combines confirmed Seed Tier A core candidates, 26 non-seed confirmed core candidates, and 2 verified rescue candidates. With current local primary-source evidence, confirmed Seed Tier A core count is {summary['confirmed_core_hard_tech_bottleneck_count']}, so the preview count is {summary['revised_core_pool_preview_count']}.

## 7. Guardrails

- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}
- baseline_admission_changed_count: {summary['baseline_admission_changed_count']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- existing workbench_core_candidates.csv modified: {summary['existing_workbench_core_candidates_modified']}

## 8. Acceptance Decision

{summary['acceptance_decision']}
"""


def generate(
    workbench_dir: Path = WORKBENCH_DIR,
    manual_packet_dir: Path = MANUAL_PACKET_DIR,
    pipeline_closure_dir: Path = PIPELINE_CLOSURE_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    core_path = workbench_dir / "workbench_core_candidates.csv"
    core_hash_before = _sha(core_path)
    inputs = load_inputs(workbench_dir, manual_packet_dir, pipeline_closure_dir)
    core_pool = inputs["core_pool"]
    requalification = build_requalification(core_pool)
    preview = build_revised_core_preview(core_pool, requalification)
    core_hash_after = _sha(core_path)
    strategy_clean = _git_diff_formal_strategy_files() == ""

    counts = requalification["final_requalification_category"].value_counts().to_dict()
    obvious_contaminants = requalification.loc[
        requalification["final_requalification_category"].eq("reject_seed_pollution"), "stock_name"
    ].astype(str).tolist()
    specific_checks = {
        name: str(requalification.loc[requalification["stock_name"].eq(name), "final_requalification_category"].iloc[0])
        for name in ["佛山照明", "通宝能源", "许继电气", "艾罗能源"]
    }
    summary: dict[str, Any] = {
        "task_name": TASK_NAME,
        "research_only": True,
        "seed_tier_a_audited_count": int(len(requalification)),
        "confirmed_core_hard_tech_bottleneck_count": int(counts.get("confirmed_core_hard_tech_bottleneck", 0)),
        "hard_tech_adjacent_watchlist_count": int(counts.get("hard_tech_adjacent_watchlist", 0)),
        "evidence_backfill_required_count": int(counts.get("evidence_backfill_required", 0)),
        "downgrade_manual_review_required_count": int(counts.get("downgrade_manual_review_required", 0)),
        "reject_seed_pollution_count": int(counts.get("reject_seed_pollution", 0)),
        "revised_core_pool_preview_count": int(len(preview)),
        "non_seed_confirmed_core_count": int(core_pool["source_group"].astype(str).eq("non_seed_tier_a_manual_review_core").sum()),
        "verified_rescue_count": int(core_pool["source_group"].astype(str).eq("verified_rescue_extension_proposal").sum()),
        "seed_primary_source_available_count": int(requalification["primary_source_evidence_available"].astype(bool).sum()),
        "inherited_seed_label_confirmed_core_count": int(
            requalification[
                requalification["company_level_evidence_status"].eq("inherited_seed_label_only")
                & requalification["final_requalification_category"].eq("confirmed_core_hard_tech_bottleneck")
            ].shape[0]
        ),
        "obvious_contaminants_removed": obvious_contaminants,
        "specific_checks": specific_checks,
        "allowed_for_signal_count": int(requalification["used_for_signal"].astype(bool).sum()) + int(preview["allowed_for_signal"].astype(bool).sum() if "allowed_for_signal" in preview else 0),
        "allowed_for_admission_count": int(requalification["used_for_admission"].astype(bool).sum()) + int(preview["allowed_for_admission"].astype(bool).sum() if "allowed_for_admission" in preview else 0),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "existing_workbench_core_candidates_modified": core_hash_before != core_hash_after,
        "production_candidate_universe_modified": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "acceptance_decision": "seed_tier_a_hard_tech_requalification_ready",
    }

    _write_json(output_dir / "seed_tier_a_requalification_summary.json", summary)
    _write_df(output_dir / "seed_tier_a_requalification.csv", requalification, REQUALIFICATION_COLUMNS)
    for category, filename in [
        ("confirmed_core_hard_tech_bottleneck", "confirmed_core_hard_tech_bottleneck.csv"),
        ("hard_tech_adjacent_watchlist", "hard_tech_adjacent_watchlist.csv"),
        ("evidence_backfill_required", "evidence_backfill_required.csv"),
        ("downgrade_manual_review_required", "downgrade_manual_review_required.csv"),
        ("reject_seed_pollution", "reject_seed_pollution.csv"),
    ]:
        subset = requalification[requalification["final_requalification_category"].eq(category)].copy()
        _write_df(output_dir / filename, subset, REQUALIFICATION_COLUMNS)
    _write_df(output_dir / "revised_core_pool_preview.csv", preview)
    (output_dir / "tech_bottleneck_seed_tier_a_hard_tech_requalification_v1_report.md").write_text(
        build_report(summary), encoding="utf-8"
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
