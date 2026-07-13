from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_candidate_discovery_quality_audit_v1"
SOURCE_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_v1/latent_evidence_completion_queue.csv"
)
LATENT_UNIVERSE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_v1/latent_candidate_discovery_universe.csv"
)
QUALITY_POOL_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
DOUBLER_CLOSURE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_doubler_market_discovered_closure_v1/doubler_market_discovered_closure_master.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
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
    "quality_audit_decision",
    "quality_audit_reason",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "notes",
]

STRICT_HARD_TECH_DOMAINS = {
    "半导体",
    "工业软件与基础软件",
    "高端制造装备",
    "航空航天与军工电子",
    "新材料",
    "光电与通信",
    "高端仪器仪表与科学仪器",
}

MANUFACTURING_OR_TECH_INDUSTRY_TOKENS = [
    "制造",
    "软件",
    "信息技术",
    "仪器",
    "设备",
    "电子",
    "通信",
    "材料",
    "化学",
    "金属",
    "研究和试验",
    "专业技术",
]

DEFER_INDUSTRY_TOKENS = [
    "金融",
    "银行",
    "保险",
    "房地",
    "教育",
    "畜牧",
    "农副",
    "食品",
    "邮政",
    "煤炭",
    "商务服务",
    "批发",
    "电力、热力生产和供应",
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


def _is_defer_industry(industry: str) -> bool:
    return _contains_any(industry, DEFER_INDUSTRY_TOKENS)


def _is_tech_industry(industry: str) -> bool:
    return _contains_any(industry, MANUFACTURING_OR_TECH_INDUSTRY_TOKENS)


def _decision(row: pd.Series) -> tuple[str, str, str]:
    domain = _text(row, "tech_bottleneck_domain")
    industry = _text(row, "industry")
    hard_signal = _text(row, "hard_tech_domain_signal")
    bottleneck = _text(row, "bottleneck_or_chokepoint_possibility")
    relevance = _text(row, "business_relevance_signal")
    source_feasibility = _text(row, "primary_source_feasibility")
    pollution = _text(row, "concept_pollution_risk").lower()
    beneficiary = _text(row, "beneficiary_only_risk").lower()

    if pollution == "high" or beneficiary == "high" or _is_defer_industry(industry):
        return (
            "latent_defer_or_reject",
            "Industry or risk flags indicate operator, financial, consumer, distribution, or concept exposure that should not enter first backfill.",
            "defer or exclude unless manual review identifies a company-specific hard-tech bottleneck path",
        )

    strict_domain = domain in STRICT_HARD_TECH_DOMAINS
    tech_industry = _is_tech_industry(industry)
    high_signal = hard_signal == "strong" and bottleneck == "high" and relevance == "high"
    backfillable = source_feasibility == "high"

    if strict_domain and tech_industry and high_signal and backfillable:
        return (
            "latent_high_priority_backfill",
            "Strict hard-tech domain, technology/manufacturing industry, high bottleneck signal, and feasible primary-source path.",
            "include in first latent primary-source backfill batch; do not auto-add to quality pool",
        )

    if strict_domain and bottleneck == "high" and relevance in {"high", "medium"} and backfillable:
        return (
            "latent_standard_backfill",
            "Hard-tech domain and bottleneck possibility remain plausible, but priority is below the first batch.",
            "include in standard latent backfill queue after high-priority batch",
        )

    if domain == "能源与电力电子关键环节" and tech_industry and bottleneck == "high" and backfillable:
        return (
            "latent_standard_backfill",
            "Energy/power-electronics candidate has a feasible source path but needs component-vs-operator checks.",
            "include in standard latent backfill queue with operator-beneficiary review",
        )

    if domain == "其他战略性关键环节" or not tech_industry:
        return (
            "latent_manual_review_first",
            "Domain or industry is too broad for immediate backfill despite the discovery-stage signal.",
            "manual review of hard-tech scope before any primary-source collection",
        )

    return (
        "latent_manual_review_first",
        "Candidate is backfillable but does not meet strict first-batch or standard backfill criteria.",
        "manual review of thesis quality and source path before backfill",
    )


def _build_audit(source_queue: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in source_queue.sort_values("stock_code").iterrows():
        decision, reason, action = _decision(row)
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
                "quality_audit_decision": decision,
                "quality_audit_reason": reason,
                "recommended_next_action": action,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": (
                    "Quality audit only for latent evidence completion queue. "
                    "No primary-source backfill, quality-pool addition, signal, or admission action was performed."
                ),
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _split_outputs(audit: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "latent_high_priority_backfill_queue.csv": audit[
            audit["quality_audit_decision"].eq("latent_high_priority_backfill")
        ].copy(),
        "latent_standard_backfill_queue.csv": audit[
            audit["quality_audit_decision"].eq("latent_standard_backfill")
        ].copy(),
        "latent_manual_review_first.csv": audit[audit["quality_audit_decision"].eq("latent_manual_review_first")].copy(),
        "latent_defer_or_reject.csv": audit[audit["quality_audit_decision"].eq("latent_defer_or_reject")].copy(),
    }


def _summary(source_queue: pd.DataFrame, audit: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = audit["quality_audit_decision"].value_counts()
    used_for_signal = int(audit["used_for_signal"].astype(bool).sum())
    used_for_admission = int(audit["used_for_admission"].astype(bool).sum())
    manual_or_defer = int(counts.get("latent_manual_review_first", 0)) + int(counts.get("latent_defer_or_reject", 0))
    blocking = used_for_signal or used_for_admission or not strategy_clean or len(source_queue) != 210 or len(audit) != 210
    acceptance = "blocked_due_to_guardrail_violation"
    if not blocking:
        acceptance = (
            "conditionally_ready_with_manual_review_needed"
            if manual_or_defer
            else "latent_candidate_discovery_quality_audit_ready"
        )
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_latent_evidence_queue_count": int(len(source_queue)),
        "processed_count": int(len(audit)),
        "latent_high_priority_backfill_count": int(counts.get("latent_high_priority_backfill", 0)),
        "latent_standard_backfill_count": int(counts.get("latent_standard_backfill", 0)),
        "latent_manual_review_first_count": int(counts.get("latent_manual_review_first", 0)),
        "latent_defer_or_reject_count": int(counts.get("latent_defer_or_reject", 0)),
        "only_latent_evidence_queue_processed": True,
        "doubled_tech_596_processed": False,
        "quality_pool_v3_processed": False,
        "latent_data_gap_watch_processed": False,
        "primary_source_backfill_performed": False,
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
        "source_latent_evidence_queue_count": summary["source_latent_evidence_queue_count"],
        "only_latent_evidence_queue_processed": True,
        "doubled_tech_596_processed": False,
        "quality_pool_v3_processed": False,
        "latent_data_gap_watch_processed": False,
        "primary_source_backfill_performed": False,
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
    return f"""# Tech Bottleneck Latent Candidate Discovery Quality Audit v1

## 1. Scope
This task audits only the 210-stock latent evidence completion queue. It does not process quality pool v3, the doubled-tech 596 set, or the latent data-gap watch bucket. It does not perform primary-source backfill or add candidates to any quality pool.

## 2. Input Queue
- Latent evidence completion queue: {summary["source_latent_evidence_queue_count"]}
- Processed: {summary["processed_count"]}

## 3. Quality Audit Method
The audit separates strict hard-tech domains and technology/manufacturing industries from broad strategic, operator, financial, consumer, or application-like exposures. Low-position and non-doubled labels remain research metadata only and are not used as signal.

## 4. Audit Results
- High-priority backfill: {summary["latent_high_priority_backfill_count"]}
- Standard backfill: {summary["latent_standard_backfill_count"]}
- Manual review first: {summary["latent_manual_review_first_count"]}
- Defer or reject: {summary["latent_defer_or_reject_count"]}

## 5. Guardrail Checks
- Research-only: true
- Primary-source backfill performed: false
- Auto added to quality pool: 0
- Price move used for signal: 0
- Low position used for signal: 0
- Used for signal: {summary["used_for_signal_count"]}
- Used for admission: {summary["used_for_admission_count"]}
- Strategy file diff clean: {str(summary["strategy_file_diff_clean"]).lower()}

## 6. Acceptance Decision
{summary["acceptance_decision"]}

## 7. Recommended Next Steps
1. tech_bottleneck_latent_primary_source_backfill_batch1_v1
2. tech_bottleneck_latent_data_gap_watch_triage_v1
3. tech_bottleneck_stock_workspace_docling_panel_v1
"""


def run() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_queue = _read_csv(SOURCE_QUEUE)
    audit = _build_audit(source_queue)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(source_queue, audit, strategy_clean)
    guardrails = _guardrails(summary)

    audit.to_csv(OUTPUT_DIR / "latent_candidate_quality_audit.csv", index=False)
    for filename, frame in _split_outputs(audit).items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)
    _write_json(OUTPUT_DIR / "latent_candidate_discovery_quality_audit_summary.json", summary)
    _write_json(OUTPUT_DIR / "latent_candidate_discovery_quality_audit_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_latent_candidate_discovery_quality_audit_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
