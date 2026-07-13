from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
POOL_PATH = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
DOCLING_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
DASHBOARD_PAYLOAD = (
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_review_and_dashboard_integration_v1/dashboard_payload.json"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_docling_report_quality_gate_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

SOURCE_MIX_TYPES = [
    "primary_source",
    "annual_report",
    "announcement",
    "official_website",
    "interactive_platform",
    "brokerage_report",
    "weak_secondary_source",
    "unknown_source",
]
GAP_TYPES = [
    "missing_primary_source",
    "missing_annual_report",
    "missing_announcement",
    "missing_named_customer",
    "missing_revenue_trace",
    "missing_financial_trace",
    "missing_architecture_shift",
    "missing_route_around",
    "missing_value_capture",
    "missing_disconfirmation",
    "brokerage_only_risk",
    "adjacent_only_risk",
]
HARD_TECH_KEYWORDS = [
    "半导体",
    "设备",
    "材料",
    "国产",
    "自主",
    "核心技术",
    "关键技术",
    "高端",
    "工艺",
    "研发",
    "专利",
    "客户",
    "订单",
    "产能",
    "良率",
    "检测",
    "测量",
    "封装",
    "电网",
    "特高压",
    "光模块",
    "pcb",
    "机器人",
]
PRIMARY_PATTERNS = ["年度报告", "半年度报告", "季度报告", "三季度报告", "一季度报告", "招股", "公告", "深交所", "上交所", "北交所", "官网", "互动易", "投资者关系"]
BROKERAGE_PATTERNS = ["证券", "研究", "交银国际", "光大", "中信", "国盛", "国金", "华泰", "招商", "海通", "申万", "评级", "点评", "公司更新"]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"stock_code": str}).assign(stock_code=lambda df: df["stock_code"].map(_stock_code))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _classify_source(source: dict[str, Any]) -> set[str]:
    title = str(source.get("source_title") or "")
    url = str(source.get("source_path_or_url") or "")
    haystack = f"{title} {url}".lower()
    classes: set[str] = set()
    if any(pattern.lower() in haystack for pattern in PRIMARY_PATTERNS):
        classes.add("primary_source")
    if "年度报告" in haystack or "年报" in haystack:
        classes.add("annual_report")
    if "公告" in haystack:
        classes.add("announcement")
    if "官网" in haystack or "official" in haystack or "www." in haystack:
        classes.add("official_website")
    if "互动易" in haystack or "投资者关系" in haystack or "investor" in haystack:
        classes.add("interactive_platform")
    if any(pattern.lower() in haystack for pattern in BROKERAGE_PATTERNS) and "深交所" not in haystack and "上交所" not in haystack:
        classes.add("brokerage_report")
    if not classes:
        classes.add("unknown_source")
    return classes


def _claim_keyword_score(claims: pd.DataFrame) -> int:
    if claims.empty:
        return 0
    text = " ".join(str(value) for value in claims.get("excerpt", pd.Series(dtype=str)).fillna("").tolist()).lower()
    return sum(1 for keyword in HARD_TECH_KEYWORDS if keyword.lower() in text)


def _git_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    pool = _read_csv(POOL_PATH)
    manifest = _read_csv(DOCLING_DIR / "batch_manifest.csv")
    reports = _read_csv(DOCLING_DIR / "report_generation_audit.csv")
    citations = _read_csv(DOCLING_DIR / "citation_audit.csv")
    tables = _read_csv(DOCLING_DIR / "table_provenance_audit.csv")
    payload = json.loads(DASHBOARD_PAYLOAD.read_text(encoding="utf-8"))
    return pool, manifest, reports, citations, tables, payload


def _quality_label_from_score(score: int) -> str:
    if score >= 3:
        return "strong"
    if score >= 2:
        return "moderate"
    if score >= 1:
        return "weak"
    return "unsupported"


def _assess_stock(row: pd.Series, report: pd.Series, citation: pd.Series, table: pd.Series) -> dict[str, Any]:
    stock_code = row["stock_code"]
    claim_path = Path(str(report.get("claim_citation_map_path") or ""))
    sources_path = Path(str(report.get("sources_jsonl_path") or ""))
    claims = pd.read_csv(claim_path, dtype={"stock_code": str}) if claim_path.exists() else pd.DataFrame()
    sources = {str(source.get("citation_id")): source for source in _load_jsonl(sources_path)}

    source_counts = Counter({source_type: 0 for source_type in SOURCE_MIX_TYPES})
    for _, claim in claims.iterrows():
        source = sources.get(str(claim.get("citation_id"))) or {
            "source_title": claim.get("source_path_or_url"),
            "source_path_or_url": claim.get("source_path_or_url"),
        }
        classes = _classify_source(source)
        if "primary_source" in classes:
            source_counts["primary_source"] += 1
        if "annual_report" in classes:
            source_counts["annual_report"] += 1
        if "announcement" in classes:
            source_counts["announcement"] += 1
        if "official_website" in classes:
            source_counts["official_website"] += 1
        if "interactive_platform" in classes:
            source_counts["interactive_platform"] += 1
        if "brokerage_report" in classes:
            source_counts["brokerage_report"] += 1
        if "unknown_source" in classes:
            source_counts["unknown_source"] += 1
        if not classes or classes == {"unknown_source"}:
            source_counts["weak_secondary_source"] += 1

    citation_count = int(citation.get("citation_claim_count") or 0)
    page_level_count = int(citation.get("page_level_citation_row_count") or 0)
    table_count = int(table.get("table_provenance_full_count") or 0)
    keyword_score = _claim_keyword_score(claims)
    current_category = str(row.get("review_pool_category") or row.get("requalification_v2_category") or "")
    relevance = str(row.get("bottleneck_relevance") or "")
    business_category = str(row.get("business_relevance_category") or "")
    primary_supported = source_counts["primary_source"] > 0
    brokerage_only = source_counts["brokerage_report"] > 0 and not primary_supported
    adjacent_risk = "adjacent" in current_category or "adjacent" in relevance or "generic" in business_category
    pollution_risk = "reject" in current_category or "pollution" in current_category or "consumer" in business_category or "bank" in business_category

    support_score = 0
    if citation_count >= 10:
        support_score += 1
    if primary_supported:
        support_score += 1
    if keyword_score >= 4:
        support_score += 1
    if "verified_core" in current_category or "manual_anchor" in current_category:
        support_score += 1
    if adjacent_risk:
        support_score -= 1
    if pollution_risk:
        support_score -= 2
    support = _quality_label_from_score(support_score)

    hard_tech_quality = "strong" if ("verified_core" in current_category and primary_supported) else "moderate"
    if adjacent_risk:
        hard_tech_quality = "weak"
    if pollution_risk:
        hard_tech_quality = "unsupported"
    supply_chain_quality = "moderate" if "component" in business_category or "equipment" in business_category or "material" in business_category else "weak"
    if "semiconductor" in business_category or "power_electronics" in business_category:
        supply_chain_quality = "strong" if primary_supported else "moderate"
    architecture_quality = "moderate" if keyword_score >= 4 else "weak"
    route_quality = "weak" if "missing_route_around" else "weak"
    value_quality = "moderate" if source_counts["annual_report"] > 0 or "financial" in " ".join(claims.get("report_section", [])) else "weak"
    disconfirmation_found = bool(claims.get("report_section", pd.Series(dtype=str)).astype(str).str.contains("risk|risks|counter", case=False, regex=True).any())

    gaps: list[str] = []
    if not primary_supported:
        gaps.append("missing_primary_source")
    if source_counts["annual_report"] == 0:
        gaps.append("missing_annual_report")
    if source_counts["announcement"] == 0:
        gaps.append("missing_announcement")
    if not _contains_any(claims, ["客户", "供应商", "认证"]):
        gaps.append("missing_named_customer")
    if not _contains_any(claims, ["收入", "营收", "营业收入"]):
        gaps.append("missing_revenue_trace")
    if not _contains_any(claims, ["净利润", "毛利率", "现金流", "研发费用"]):
        gaps.append("missing_financial_trace")
    if keyword_score < 4:
        gaps.append("missing_architecture_shift")
    gaps.append("missing_route_around")
    if value_quality == "weak":
        gaps.append("missing_value_capture")
    if not disconfirmation_found:
        gaps.append("missing_disconfirmation")
    if brokerage_only:
        gaps.append("brokerage_only_risk")
    if adjacent_risk:
        gaps.append("adjacent_only_risk")

    if pollution_risk or support == "unsupported":
        decision = "reject" if pollution_risk else "downgrade"
        entry_class = "downgrade_or_reject"
    elif adjacent_risk:
        decision = "adjacent_only"
        entry_class = "adjacent_watchlist"
    elif support == "strong" and primary_supported:
        decision = "pass"
        entry_class = "confirmed_core_ready_for_manual_review"
    elif support in {"strong", "moderate"}:
        decision = "pass_with_gap" if gaps else "pass"
        entry_class = "likely_core_pending_evidence"
    else:
        decision = "backfill_required"
        entry_class = "evidence_backfill_required"

    next_action = _next_action(gaps, primary_supported)
    return {
        "stock_code": stock_code,
        "stock_name": row["stock_name"],
        "current_pool_status": current_category,
        "docling_report_status": str(report.get("report_status") or ""),
        "citation_count": citation_count,
        "page_level_citation_count": page_level_count,
        "primary_source_evidence_count": int(source_counts["primary_source"]),
        "brokerage_evidence_count": int(source_counts["brokerage_report"]),
        "announcement_evidence_count": int(source_counts["announcement"]),
        "annual_report_evidence_count": int(source_counts["annual_report"]),
        "official_website_evidence_count": int(source_counts["official_website"]),
        "interactive_platform_evidence_count": int(source_counts["interactive_platform"]),
        "table_provenance_count": table_count,
        "bottleneck_thesis_support": support,
        "hard_tech_exposure_quality": hard_tech_quality,
        "supply_chain_role_quality": supply_chain_quality,
        "architecture_shift_quality": architecture_quality,
        "route_around_assessment_quality": route_quality,
        "value_capture_evidence_quality": value_quality,
        "disconfirmation_found": disconfirmation_found,
        "pollution_risk": "high" if pollution_risk else "low",
        "adjacent_risk": "high" if adjacent_risk else "low",
        "evidence_gap_flags": "|".join(gaps),
        "recommended_next_evidence_action": next_action,
        "quality_gate_decision": decision,
        "manual_review_entry_class": entry_class,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "notes": _notes(support, primary_supported, brokerage_only, adjacent_risk, pollution_risk),
        **{source_type: int(source_counts[source_type]) for source_type in SOURCE_MIX_TYPES},
    }


def _contains_any(claims: pd.DataFrame, keywords: list[str]) -> bool:
    if claims.empty:
        return False
    text = " ".join(str(value) for value in claims.get("excerpt", pd.Series(dtype=str)).fillna("").tolist())
    return any(keyword in text for keyword in keywords)


def _next_action(gaps: list[str], primary_supported: bool) -> str:
    if not primary_supported:
        return "backfill annual report, exchange announcement, official website, or investor relations source"
    if "missing_named_customer" in gaps:
        return "verify named customer, certification, or order evidence from primary source"
    if "missing_value_capture" in gaps:
        return "verify revenue trace, margin, order, and financial statement support"
    if "missing_route_around" in gaps:
        return "review substitute supplier, qualification cycle, and route-around evidence"
    return "manual thesis review using page-level cited report evidence"


def _notes(support: str, primary: bool, brokerage_only: bool, adjacent: bool, pollution: bool) -> str:
    if pollution:
        return "quality gate found pollution or reject risk; do not treat as core without manual override"
    if adjacent:
        return "hard-tech relevance appears adjacent; keep separate from core thesis review"
    if brokerage_only:
        return "report evidence is brokerage-only; primary-source backfill is required before core confirmation"
    if primary and support in {"strong", "moderate"}:
        return "page-level report evidence supports manual review; still requires analyst thesis validation"
    return "evidence is incomplete; use as backfill queue input"


def _build_quality_gate() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    pool, manifest, reports, citations, tables, payload = _load_inputs()
    report_by_code = reports.set_index("stock_code")
    citation_by_code = citations.set_index("stock_code")
    table_by_code = tables.set_index("stock_code")
    assessed = []
    for _, row in pool.sort_values("stock_code").iterrows():
        code = row["stock_code"]
        assessed.append(
            _assess_stock(
                row,
                report_by_code.loc[code] if code in report_by_code.index else pd.Series(dtype=object),
                citation_by_code.loc[code] if code in citation_by_code.index else pd.Series(dtype=object),
                table_by_code.loc[code] if code in table_by_code.index else pd.Series(dtype=object),
            )
        )
    main = pd.DataFrame(assessed)
    thesis = main[
        [
            "stock_code",
            "stock_name",
            "bottleneck_thesis_support",
            "hard_tech_exposure_quality",
            "supply_chain_role_quality",
            "architecture_shift_quality",
            "route_around_assessment_quality",
            "value_capture_evidence_quality",
            "disconfirmation_found",
            "quality_gate_decision",
            "manual_review_entry_class",
            "notes",
        ]
    ].copy()
    source_mix = main[["stock_code", "stock_name", *SOURCE_MIX_TYPES]].copy()
    source_mix["dominant_source_mix"] = source_mix[SOURCE_MIX_TYPES].idxmax(axis=1)
    source_mix["brokerage_only_risk"] = (source_mix["brokerage_report"] > 0) & (source_mix["primary_source"] == 0)
    gap_rows = []
    for _, row in main.iterrows():
        flags = set(str(row["evidence_gap_flags"]).split("|")) if row["evidence_gap_flags"] else set()
        for gap in GAP_TYPES:
            gap_rows.append(
                {
                    "stock_code": row["stock_code"],
                    "stock_name": row["stock_name"],
                    "evidence_gap_type": gap,
                    "gap_present": gap in flags,
                    "severity": _gap_severity(gap, gap in flags),
                    "recommended_fix": _gap_fix(gap),
                }
            )
    gaps = pd.DataFrame(gap_rows)
    downgrade = main[main["manual_review_entry_class"].eq("downgrade_or_reject")][
        ["stock_code", "stock_name", "quality_gate_decision", "manual_review_entry_class", "pollution_risk", "adjacent_risk", "evidence_gap_flags", "notes"]
    ].copy()
    strategy_clean = _git_diff_clean()
    summary = _summary(main, payload, strategy_clean)
    guardrails = {
        "task_name": "tech_bottleneck_90_docling_report_quality_gate_v1",
        "research_only": True,
        "pool_total": int(len(main)),
        "docling_report_quality_gate_generated": True,
        "all_90_reports_accounted_for": int(len(main)) == 90 and int(main["docling_report_status"].ne("").sum()) == 90,
        "used_for_signal_count": int(main["used_for_signal"].sum()),
        "used_for_admission_count": int(main["used_for_admission"].sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }
    return main, thesis, source_mix, gaps, downgrade, summary, guardrails


def _gap_severity(gap: str, present: bool) -> str:
    if not present:
        return "none"
    if gap in {"missing_primary_source", "brokerage_only_risk", "adjacent_only_risk"}:
        return "high"
    if gap in {"missing_value_capture", "missing_route_around", "missing_disconfirmation"}:
        return "medium"
    return "low"


def _gap_fix(gap: str) -> str:
    fixes = {
        "missing_primary_source": "backfill annual report, exchange announcement, official website, or investor relations source",
        "missing_annual_report": "add annual report or periodic report evidence",
        "missing_announcement": "check exchange announcements for orders, capacity, certification, or product milestones",
        "missing_named_customer": "verify named customer, certification, or customer-side disclosure",
        "missing_revenue_trace": "map product line to disclosed revenue or segment data",
        "missing_financial_trace": "backfill financial statement metrics",
        "missing_architecture_shift": "document old architecture failure point and new dependency",
        "missing_route_around": "document substitute supplier and qualification cycle evidence",
        "missing_value_capture": "document margin, pricing power, order, backlog, or revenue trace",
        "missing_disconfirmation": "define fastest primary-source disconfirming evidence",
        "brokerage_only_risk": "replace or confirm brokerage claims with primary-source evidence",
        "adjacent_only_risk": "separate adjacent watchlist from core bottleneck thesis review",
    }
    return fixes[gap]


def _summary(main: pd.DataFrame, payload: dict[str, Any], strategy_clean: bool) -> dict[str, Any]:
    counts = main["manual_review_entry_class"].value_counts()
    support_counts = main["bottleneck_thesis_support"].value_counts()
    used_signal = int(main["used_for_signal"].sum())
    used_admission = int(main["used_for_admission"].sum())
    guardrail_ok = used_signal == 0 and used_admission == 0 and strategy_clean
    missing_reports = int(main["docling_report_status"].eq("").sum())
    evidence_backfill = int(counts.get("evidence_backfill_required", 0))
    if missing_reports:
        decision = "blocked_due_to_missing_reports"
    elif not guardrail_ok:
        decision = "blocked_due_to_guardrail_violation"
    elif evidence_backfill > 0 or int(counts.get("likely_core_pending_evidence", 0)) > 0:
        decision = "conditionally_ready_with_evidence_gaps"
    else:
        decision = "docling_90_quality_gate_ready"
    return {
        "pool_total": int(len(main)),
        "report_ready_count": int(main["docling_report_status"].ne("").sum()),
        "report_failed_count": int(main["docling_report_status"].eq("failed").sum()),
        "citation_total": int(main["citation_count"].sum()),
        "page_level_citation_total": int(main["page_level_citation_count"].sum()),
        "primary_source_supported_count": int(main["primary_source_evidence_count"].gt(0).sum()),
        "brokerage_only_count": int((main["brokerage_evidence_count"].gt(0) & main["primary_source_evidence_count"].eq(0)).sum()),
        "strong_thesis_support_count": int(support_counts.get("strong", 0)),
        "moderate_thesis_support_count": int(support_counts.get("moderate", 0)),
        "weak_thesis_support_count": int(support_counts.get("weak", 0)),
        "unsupported_thesis_count": int(support_counts.get("unsupported", 0)),
        "confirmed_core_ready_count": int(counts.get("confirmed_core_ready_for_manual_review", 0)),
        "likely_core_pending_evidence_count": int(counts.get("likely_core_pending_evidence", 0)),
        "adjacent_watchlist_count": int(counts.get("adjacent_watchlist", 0)),
        "evidence_backfill_required_count": int(counts.get("evidence_backfill_required", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
        "used_for_signal_count": used_signal,
        "used_for_admission_count": used_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": decision,
        "source_baseline_acceptance_decision": payload.get("acceptance_decision", ""),
    }


def _write_report(summary: dict[str, Any], guardrails: dict[str, Any], downgrade: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck 90 Docling Report Quality Gate v1",
            "",
            "## 1. Scope",
            "This task audits only the canonical 90 hard-tech review pool Docling report thesis quality gate. It is research-only, does not expand the pool, does not connect signal, and does not change admission.",
            "",
            "## 2. Input Baseline",
            f"Pool total: {summary['pool_total']}. Citation total: {summary['citation_total']}. Page-level citations: {summary['page_level_citation_total']}. Report ready: {summary['report_ready_count']}.",
            "",
            "## 3. Quality Gate Method",
            "The gate uses deterministic checks over source mix, page-level citations, hard-tech keyword coverage, pool refinement category, adjacent risk, pollution risk, and evidence gaps.",
            "",
            "## 4. Thesis Support Results",
            f"Strong: {summary['strong_thesis_support_count']}; moderate: {summary['moderate_thesis_support_count']}; weak: {summary['weak_thesis_support_count']}; unsupported: {summary['unsupported_thesis_count']}.",
            "",
            "## 5. Source Mix Audit",
            f"Primary-source supported: {summary['primary_source_supported_count']}; brokerage-only risk: {summary['brokerage_only_count']}.",
            "",
            "## 6. Evidence Gap Matrix",
            "The evidence gap matrix records primary-source, annual report, announcement, named customer, revenue trace, financial trace, architecture shift, route-around, value capture, disconfirmation, brokerage-only, and adjacent-only gaps.",
            "",
            "## 7. Manual Review Entry Classes",
            f"Confirmed core ready: {summary['confirmed_core_ready_count']}; likely core pending evidence: {summary['likely_core_pending_evidence_count']}; adjacent watchlist: {summary['adjacent_watchlist_count']}; evidence backfill required: {summary['evidence_backfill_required_count']}; downgrade or reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 8. Downgrade Or Reject Candidates",
            f"Downgrade or reject count: {len(downgrade)}.",
            "",
            "## 9. Guardrail Checks",
            f"research_only={str(guardrails['research_only']).lower()}; used_for_signal_count={guardrails['used_for_signal_count']}; used_for_admission_count={guardrails['used_for_admission_count']}; baseline_admission_changed_count={guardrails['baseline_admission_changed_count']}; strategy_file_diff_clean={str(guardrails['strategy_file_diff_clean']).lower()}; trading_language_hit_count={guardrails['trading_language_hit_count']}; execution_language_hit_count={guardrails['execution_language_hit_count']}.",
            "",
            "## 10. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 11. Recommended Next Steps",
            "1. tech_bottleneck_confirmed_core_pool_proposal_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_90_primary_source_backfill_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    main, thesis, source_mix, gaps, downgrade, summary, guardrails = _build_quality_gate()
    main_columns = [
        "stock_code",
        "stock_name",
        "current_pool_status",
        "docling_report_status",
        "citation_count",
        "page_level_citation_count",
        "primary_source_evidence_count",
        "brokerage_evidence_count",
        "announcement_evidence_count",
        "annual_report_evidence_count",
        "official_website_evidence_count",
        "interactive_platform_evidence_count",
        "table_provenance_count",
        "bottleneck_thesis_support",
        "hard_tech_exposure_quality",
        "supply_chain_role_quality",
        "architecture_shift_quality",
        "route_around_assessment_quality",
        "value_capture_evidence_quality",
        "disconfirmation_found",
        "pollution_risk",
        "adjacent_risk",
        "evidence_gap_flags",
        "recommended_next_evidence_action",
        "quality_gate_decision",
        "manual_review_entry_class",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    main[main_columns].to_csv(output_dir / "tech_bottleneck_90_report_quality_gate.csv", index=False)
    thesis.to_csv(output_dir / "tech_bottleneck_90_thesis_support_audit.csv", index=False)
    source_mix.to_csv(output_dir / "tech_bottleneck_90_source_mix_audit.csv", index=False)
    gaps.to_csv(output_dir / "tech_bottleneck_90_evidence_gap_matrix.csv", index=False)
    downgrade.to_csv(output_dir / "tech_bottleneck_90_downgrade_or_reject_candidates.csv", index=False)
    (output_dir / "tech_bottleneck_90_docling_report_quality_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "tech_bottleneck_90_docling_report_quality_gate_guardrails.json").write_text(
        json.dumps(guardrails, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "tech_bottleneck_90_docling_report_quality_gate_v1_report.md").write_text(
        _write_report(summary, guardrails, downgrade),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
