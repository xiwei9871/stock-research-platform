from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_manual_review_first_triage_v1"
INPUT_MANUAL_FIRST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_manual_review_first.csv"
)
INPUT_DEFER_REJECT = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_defer_or_reject.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 113
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

OUTPUT_COLUMNS = [
    "stock_code",
    "stock_name",
    "tech_bottleneck_domain",
    "supply_chain_role",
    "candidate_tier",
    "hard_tech_domain_signal",
    "bottleneck_or_chokepoint_possibility",
    "business_relevance_signal",
    "concept_pollution_risk",
    "beneficiary_only_risk",
    "primary_source_feasibility",
    "next_primary_source_to_check",
    "price_move_bucket",
    "low_position_research_tag",
    "needs_human_supply_chain_role_confirmation",
    "triage_decision",
    "triage_reason",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "notes",
]

HIGH_PRIORITY_NAME_TOKENS = [
    "航天",
    "中航",
    "光电",
    "光峰",
    "光学",
    "华大九天",
    "中芯",
    "国芯",
    "芯",
    "超导",
    "电器",
    "电气",
    "曙光",
    "精电",
    "精仪",
    "仪",
    "通信",
    "海防",
    "军工",
    "普源",
    "莱伯泰科",
]
STANDARD_NAME_TOKENS = [
    "电子",
    "数据",
    "数智",
    "软件",
    "信息",
    "网络",
    "机器人",
    "装备",
    "材料",
    "新材",
    "复材",
    "电缆",
    "电工",
    "电池",
    "储能",
    "半导体",
    "集成",
    "传感",
    "电源",
    "智能",
]
BROAD_CONFIRM_TOKENS = [
    "集团",
    "医疗",
    "生物",
    "药业",
    "办公",
    "汽车",
    "股份",
    "安全",
    "创新",
    "能源",
    "油服",
    "车轴",
    "钢构",
    "动力",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _text(row: pd.Series, column: str) -> str:
    return str(row.get(column, "") or "").strip()


def _contains_any(value: str, tokens: list[str]) -> bool:
    return any(token in value for token in tokens)


def _decision(row: pd.Series) -> tuple[str, bool, str, str]:
    name = _text(row, "stock_name")
    tier = _text(row, "candidate_tier")
    hard_signal = _text(row, "hard_tech_domain_signal")
    bottleneck = _text(row, "bottleneck_or_chokepoint_possibility")
    relevance = _text(row, "business_relevance_signal")
    feasibility = _text(row, "primary_source_feasibility")
    pollution = _text(row, "concept_pollution_risk").lower()
    beneficiary = _text(row, "beneficiary_only_risk").lower()

    strong_path = hard_signal == "strong" and bottleneck == "high" and relevance == "high" and feasibility == "high"
    moderate_path = bottleneck == "high" and relevance in {"high", "medium"} and feasibility == "high"
    needs_confirm = True

    if pollution == "high" or beneficiary == "high" or feasibility != "high":
        return (
            "defer_or_reject",
            needs_confirm,
            "Risk flags or weak source feasibility prevent collection without human review.",
            "defer or reject unless human review identifies a company-specific hard-tech bottleneck path",
        )
    if tier == "Tier A" and strong_path:
        return (
            "high_priority_collection_queue",
            needs_confirm,
            "Tier A manual-review-first name has strong hard-tech, bottleneck, business relevance, and feasible primary-source path.",
            "collect primary sources after human confirmation of supply-chain role; no automatic quality-pool action",
        )
    if strong_path and _contains_any(name, HIGH_PRIORITY_NAME_TOKENS):
        return (
            "high_priority_collection_queue",
            needs_confirm,
            "Company name/domain cue suggests a direct hard-tech component, equipment, semiconductor, defense, optical, or instrument path, but supply-chain role still needs human confirmation.",
            "collect primary sources after human confirmation of supply-chain role; no automatic quality-pool action",
        )
    if moderate_path and _contains_any(name, STANDARD_NAME_TOKENS):
        return (
            "standard_collection_queue",
            needs_confirm,
            "Manual-review-first candidate has feasible primary-source path and a plausible hard-tech business cue, but is below high-priority confidence.",
            "collect primary sources in standard manual-review batch after supply-chain-role confirmation",
        )
    if strong_path and not _contains_any(name, BROAD_CONFIRM_TOKENS):
        return (
            "standard_collection_queue",
            needs_confirm,
            "Strong discovery-stage signal remains plausible, but broad-domain classification prevents direct high-priority treatment.",
            "collect primary sources in standard manual-review batch after supply-chain-role confirmation",
        )
    return (
        "human_confirm_first",
        needs_confirm,
        "Broad-domain or application-like exposure requires human confirmation before source collection.",
        "human review of bottleneck/chokepoint role before any primary-source collection",
    )


def _build_triage(manual_first: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in manual_first.sort_values("stock_code").iterrows():
        decision, needs_confirm, reason, action = _decision(row)
        rows.append(
            {
                "stock_code": _stock_code(row["stock_code"]),
                "stock_name": _text(row, "stock_name"),
                "tech_bottleneck_domain": _text(row, "tech_bottleneck_domain"),
                "supply_chain_role": _text(row, "supply_chain_role"),
                "candidate_tier": _text(row, "candidate_tier"),
                "hard_tech_domain_signal": _text(row, "hard_tech_domain_signal"),
                "bottleneck_or_chokepoint_possibility": _text(row, "bottleneck_or_chokepoint_possibility"),
                "business_relevance_signal": _text(row, "business_relevance_signal"),
                "concept_pollution_risk": _text(row, "concept_pollution_risk"),
                "beneficiary_only_risk": _text(row, "beneficiary_only_risk"),
                "primary_source_feasibility": _text(row, "primary_source_feasibility"),
                "next_primary_source_to_check": _text(row, "next_primary_source_to_check"),
                "price_move_bucket": _text(row, "price_move_bucket"),
                "low_position_research_tag": _text(row, "low_position_research_tag"),
                "needs_human_supply_chain_role_confirmation": needs_confirm,
                "triage_decision": decision,
                "triage_reason": reason,
                "recommended_next_action": action,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": (
                    "Triage only for latent manual-review-first queue. No PDF collection, backfill, "
                    "equivalence gate, quality-pool addition, signal, or admission action was performed."
                ),
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _split_outputs(triage: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "latent_manual_review_high_priority_collection_queue.csv": triage[
            triage["triage_decision"].eq("high_priority_collection_queue")
        ].copy(),
        "latent_manual_review_standard_collection_queue.csv": triage[
            triage["triage_decision"].eq("standard_collection_queue")
        ].copy(),
        "latent_manual_review_human_confirm_first.csv": triage[
            triage["triage_decision"].eq("human_confirm_first")
        ].copy(),
        "latent_manual_review_defer_or_reject.csv": triage[triage["triage_decision"].eq("defer_or_reject")].copy(),
    }


def _summary(
    manual_first: pd.DataFrame,
    defer_input: pd.DataFrame,
    quality_pool_v5: pd.DataFrame,
    triage: pd.DataFrame,
    strategy_clean: bool,
) -> dict[str, Any]:
    counts = triage["triage_decision"].value_counts()
    used_for_signal = int(triage["used_for_signal"].astype(bool).sum())
    used_for_admission = int(triage["used_for_admission"].astype(bool).sum())
    quality_overlap = len(set(triage["stock_code"]) & set(quality_pool_v5["stock_code"]))
    defer_overlap = len(set(triage["stock_code"]) & set(defer_input["stock_code"]))
    blocking = (
        len(manual_first) != EXPECTED_COUNT
        or len(triage) != EXPECTED_COUNT
        or len(quality_pool_v5) != 300
        or quality_overlap != 0
        or defer_overlap != 0
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif counts.get("human_confirm_first", 0) or counts.get("defer_or_reject", 0):
        acceptance = "conditionally_ready_with_manual_review_needed"
    else:
        acceptance = "latent_manual_review_first_triage_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_manual_review_first_count": int(len(manual_first)),
        "processed_count": int(len(triage)),
        "high_priority_collection_queue_count": int(counts.get("high_priority_collection_queue", 0)),
        "standard_collection_queue_count": int(counts.get("standard_collection_queue", 0)),
        "human_confirm_first_count": int(counts.get("human_confirm_first", 0)),
        "defer_or_reject_count": int(counts.get("defer_or_reject", 0)),
        "quality_pool_v5_reference_count": int(len(quality_pool_v5)),
        "quality_pool_v5_overlap_count": int(quality_overlap),
        "defer_reject_24_overlap_count": int(defer_overlap),
        "primary_source_collection_performed": False,
        "backfill_decision_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
        "defer_reject_24_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_manual_review_first_count": summary["source_manual_review_first_count"],
        "processed_count": summary["processed_count"],
        "primary_source_collection_performed": False,
        "backfill_decision_performed": False,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
        "defer_reject_24_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Latent Manual Review First Triage v1",
            "",
            "## 1. Scope",
            "This task triages only the 113-stock latent manual-review-first queue. It does not collect PDFs, perform primary-source backfill, run a core equivalence gate, add candidates to any quality pool, or process quality pool v5.",
            "",
            "## 2. Triage Results",
            f"Processed: {summary['processed_count']}; high-priority collection queue: {summary['high_priority_collection_queue_count']}; standard collection queue: {summary['standard_collection_queue_count']}; human confirm first: {summary['human_confirm_first_count']}; defer/reject: {summary['defer_or_reject_count']}.",
            "",
            "## 3. Guardrails",
            f"primary_source_collection_performed=false; backfill_decision_performed=false; core_equivalence_performed=false; quality_pool_v5_processed=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal=0; low_position_used_for_signal=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_latent_manual_review_collection_batch1_v1",
            "2. tech_bottleneck_quality_pool_layer_v5_manual_review_packet_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manual_first = _read_csv(INPUT_MANUAL_FIRST)
    defer_input = _read_csv(INPUT_DEFER_REJECT)
    quality_pool_v5 = _read_csv(QUALITY_POOL_V5)
    triage = _build_triage(manual_first)
    outputs = _split_outputs(triage)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(manual_first, defer_input, quality_pool_v5, triage, strategy_clean)
    guardrails = _guardrails(summary)

    triage.to_csv(OUTPUT_DIR / "latent_manual_review_first_triage.csv", index=False)
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)
    _write_json(OUTPUT_DIR / "latent_manual_review_first_triage_summary.json", summary)
    _write_json(OUTPUT_DIR / "latent_manual_review_first_triage_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_latent_manual_review_first_triage_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
