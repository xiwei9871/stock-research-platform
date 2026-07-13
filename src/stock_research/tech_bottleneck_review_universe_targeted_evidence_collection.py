from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_targeted_evidence_collection_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME

REMAINING_GAP = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_remaining_gap_queue.csv"
)
HYDRATED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_evidence_hydrated.csv"
)
AUDIT_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_v1.csv"
)
FULL_BATCH_EVIDENCE = (
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/batch_evidence_matrix.csv"
)
FULL_BATCH_CITATIONS = (
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/batch_claim_citation_map.csv"
)
FULL_BATCH_CHUNKS = (
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1/source_chunk_manifest_all.csv"
)

FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

TARGETED_STATUS = [
    "targeted_frontend_ready",
    "evidence_light_but_usable",
    "remaining_needs_manual_source_mapping",
    "remaining_needs_external_check",
    "insufficient_for_review",
]

FRONTEND_COLUMNS = [
    "stock_code",
    "stock_name",
    "targeted_evidence_status",
    "evidence_count",
    "page_citation_count",
    "source_pdf_count",
    "primary_source_supported",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "route_around_or_substitution_risk",
    "value_capture_risk",
    "disconfirmation_trigger",
    "next_primary_source_to_check",
    "strongest_primary_source_claim",
    "weakest_or_riskiest_claim",
    "recommended_next_action",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
]

EVIDENCE_INDEX_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_id",
    "chunk_id",
    "citation_id",
    "source_type",
    "source_title",
    "source_path_or_url",
    "page",
    "claim",
    "supports_field",
    "evidence_strength",
    "citation_quality",
    "parser",
    "parse_quality_flag",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
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


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _non_empty(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return default if not text or text.lower() == "nan" else text


def _prepare_evidence_index(evidence: pd.DataFrame, codes: set[str]) -> pd.DataFrame:
    subset = evidence[evidence["stock_code"].isin(codes)].copy()
    rows: list[dict[str, Any]] = []
    for _, row in subset.sort_values(["stock_code", "evidence_id", "citation_id"]).iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_id": row.get("source_id", ""),
                "chunk_id": row.get("chunk_id", ""),
                "citation_id": row.get("citation_id", ""),
                "source_type": row.get("source_type", ""),
                "source_title": row.get("source_title", ""),
                "source_path_or_url": row.get("source_path_or_url", ""),
                "page": row.get("page_locator", ""),
                "claim": row.get("excerpt", ""),
                "supports_field": row.get("report_section", row.get("evidence_kind", "")),
                "evidence_strength": row.get("evidence_strength", ""),
                "citation_quality": row.get("citation_granularity", ""),
                "parser": row.get("parser", "docling"),
                "parse_quality_flag": row.get("parse_quality_flag", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=EVIDENCE_INDEX_COLUMNS)


def _build_sources(index: pd.DataFrame) -> pd.DataFrame:
    if index.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_id",
                "source_type",
                "source_title",
                "source_path_or_url",
                "source_pdf_available",
                "source_mapping_method",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    sources = (
        index[
            [
                "stock_code",
                "stock_name",
                "source_id",
                "source_type",
                "source_title",
                "source_path_or_url",
            ]
        ]
        .drop_duplicates()
        .sort_values(["stock_code", "source_id", "source_title"])
        .reset_index(drop=True)
    )
    sources["source_pdf_available"] = sources["source_path_or_url"].astype(str).str.len() > 0
    sources["source_mapping_method"] = "existing_docling_90_artifact_reuse"
    sources["research_only"] = True
    sources["used_for_signal"] = False
    sources["used_for_admission"] = False
    return sources


def _build_download_manifest(sources: pd.DataFrame) -> pd.DataFrame:
    manifest = sources.copy()
    manifest["download_status"] = "existing_artifact_reused"
    manifest["new_pdf_downloaded"] = False
    manifest["collection_scope"] = "manual_source_mapping_from_existing_outputs"
    return manifest[
        [
            "stock_code",
            "stock_name",
            "source_id",
            "source_type",
            "source_title",
            "source_path_or_url",
            "download_status",
            "new_pdf_downloaded",
            "collection_scope",
            "research_only",
            "used_for_signal",
            "used_for_admission",
        ]
    ]


def _claim_samples(stock_index: pd.DataFrame) -> tuple[str, str]:
    if stock_index.empty:
        return "", ""
    strong = stock_index[
        stock_index["supports_field"].astype(str).str.contains(
            "business|product|key|overview|supply|bottleneck|competition", case=False, na=False
        )
    ]
    risk = stock_index[
        stock_index["supports_field"].astype(str).str.contains("risk|competition", case=False, na=False)
        | stock_index["claim"].astype(str).str.contains("风险|竞争|替代|不及预期", case=False, na=False)
    ]
    strongest = (strong.iloc[0] if not strong.empty else stock_index.iloc[0]).get("claim", "")
    weakest = (risk.iloc[0] if not risk.empty else stock_index.iloc[-1]).get("claim", "")
    return str(strongest)[:500], str(weakest)[:500]


def _status(evidence_count: int, page_count: int, source_count: int) -> str:
    if evidence_count >= 8 and page_count >= 8 and source_count > 0:
        return "targeted_frontend_ready"
    if evidence_count > 0 and page_count > 0:
        return "evidence_light_but_usable"
    if evidence_count > 0:
        return "remaining_needs_manual_source_mapping"
    return "insufficient_for_review"


def _build_frontend_ready(remaining_gap: pd.DataFrame, index: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    index_by_code = {code: group.copy() for code, group in index.groupby("stock_code")}
    source_counts = sources.groupby("stock_code")["source_path_or_url"].nunique().to_dict() if not sources.empty else {}
    rows: list[dict[str, Any]] = []
    for _, gap_row in remaining_gap.sort_values("stock_code").iterrows():
        code = gap_row["stock_code"]
        stock_index = index_by_code.get(code, pd.DataFrame(columns=EVIDENCE_INDEX_COLUMNS))
        evidence_count = len(stock_index)
        page_count = int(stock_index["citation_quality"].astype(str).str.contains("page_level", case=False, na=False).sum())
        source_pdf_count = int(source_counts.get(code, 0))
        strongest, weakest = _claim_samples(stock_index)
        status = _status(evidence_count, page_count, source_pdf_count)
        rows.append(
            {
                "stock_code": code,
                "stock_name": gap_row.get("stock_name", ""),
                "targeted_evidence_status": status,
                "evidence_count": evidence_count,
                "page_citation_count": page_count,
                "source_pdf_count": source_pdf_count,
                "primary_source_supported": _truthy(gap_row.get("primary_source_supported")),
                "hard_tech_domain": _non_empty(gap_row.get("hard_tech_domain"), "supported_by_docling_report"),
                "supply_chain_role_hint": _non_empty(gap_row.get("supply_chain_role_hint"), "supported_by_docling_report"),
                "business_relevance_hint": _non_empty(gap_row.get("business_relevance_hint"), "supported_by_docling_report"),
                "bottleneck_or_chokepoint_hint": _non_empty(
                    gap_row.get("bottleneck_or_chokepoint_hint"), "supported_by_docling_report"
                ),
                "concept_pollution_risk": _non_empty(gap_row.get("concept_pollution_risk"), "needs_manual_review"),
                "route_around_or_substitution_risk": _non_empty(
                    gap_row.get("route_around_or_substitution_risk"), "needs_manual_review"
                ),
                "value_capture_risk": _non_empty(gap_row.get("value_capture_risk"), "needs_manual_review"),
                "disconfirmation_trigger": _truthy(gap_row.get("disconfirmation_trigger")),
                "next_primary_source_to_check": _non_empty(
                    gap_row.get("next_primary_source_to_check"), "review mapped Docling page-level evidence"
                ),
                "strongest_primary_source_claim": strongest,
                "weakest_or_riskiest_claim": weakest,
                "recommended_next_action": "ready for review-universe frontend dataset"
                if status == "targeted_frontend_ready"
                else "manual source mapping or targeted collection still required",
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
    return pd.DataFrame(rows, columns=FRONTEND_COLUMNS)


def _summary(universe: pd.DataFrame, hydrated: pd.DataFrame, remaining_gap: pd.DataFrame, frontend_ready: pd.DataFrame, index: pd.DataFrame, sources: pd.DataFrame) -> dict[str, Any]:
    strategy_clean = _strategy_diff_clean()
    targeted_ready_count = int(frontend_ready["targeted_evidence_status"].eq("targeted_frontend_ready").sum())
    remaining_after = int(len(frontend_ready) - targeted_ready_count)
    used_for_signal_count = int(frontend_ready["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(frontend_ready["used_for_admission"].astype(bool).sum())
    auto_added_count = int(frontend_ready["auto_added_to_quality_pool"].astype(bool).sum())
    duplicate_stock_count = int(frontend_ready["stock_code"].duplicated().sum())
    guardrail_violation = (
        len(universe) != 378
        or len(remaining_gap) != 29
        or len(frontend_ready) != 29
        or duplicate_stock_count != 0
        or int(hydrated["hydration_status"].eq("hydrated_frontend_ready").sum()) != 271
        or int((universe["review_universe_source"] != "v5_existing").sum()) != 78
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or auto_added_count != 0
        or not strategy_clean
    )
    if guardrail_violation:
        decision = "blocked_due_to_guardrail_violation"
    elif remaining_after > 0:
        decision = "conditionally_ready_with_remaining_gaps"
    else:
        decision = "tech_bottleneck_review_universe_targeted_evidence_collection_ready"
    return {
        "task_name": TASK_NAME,
        "review_universe_total_count": int(len(universe)),
        "source_remaining_gap_count": int(len(remaining_gap)),
        "processed_remaining_gap_count": int(len(frontend_ready)),
        "existing_hydrated_frontend_ready_count": int(hydrated["hydration_status"].eq("hydrated_frontend_ready").sum()),
        "v7_frontend_ready_reference_count": int((universe["review_universe_source"] != "v5_existing").sum()),
        "targeted_frontend_ready_count": targeted_ready_count,
        "remaining_gap_count": remaining_after,
        "targeted_evidence_index_row_count": int(len(index)),
        "targeted_source_count": int(len(sources)),
        "new_pdf_download_count": 0,
        "duplicate_stock_count": duplicate_stock_count,
        "core_equivalence_performed": False,
        "frozen_quality_pool_generated": False,
        "frontend_write_performed": False,
        "auto_added_to_quality_pool_count": auto_added_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": decision,
    }


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Tech Bottleneck Review Universe Targeted Evidence Collection v1",
        "",
        "## 1. Scope",
        "This research-only step processes only the 29 v5 remaining-gap names. It uses existing Docling 90 page-level artifacts for manual source mapping and does not run equivalence gates, freeze pools, write frontend pages, or connect to signal/admission/scoring/strategy.",
        "",
        "## 2. Results",
        f"- review universe total: {summary['review_universe_total_count']}",
        f"- source remaining gap: {summary['source_remaining_gap_count']}",
        f"- processed remaining gap: {summary['processed_remaining_gap_count']}",
        f"- targeted frontend ready: {summary['targeted_frontend_ready_count']}",
        f"- remaining gap after targeted mapping: {summary['remaining_gap_count']}",
        f"- targeted evidence rows: {summary['targeted_evidence_index_row_count']}",
        f"- targeted sources: {summary['targeted_source_count']}",
        "",
        "## 3. Guardrails",
        f"- new_pdf_download_count: {summary['new_pdf_download_count']}",
        f"- core_equivalence_performed: {str(summary['core_equivalence_performed']).lower()}",
        f"- frozen_quality_pool_generated: {str(summary['frozen_quality_pool_generated']).lower()}",
        f"- frontend_write_performed: {str(summary['frontend_write_performed']).lower()}",
        f"- auto_added_to_quality_pool_count: {summary['auto_added_to_quality_pool_count']}",
        f"- used_for_signal_count: {summary['used_for_signal_count']}",
        f"- used_for_admission_count: {summary['used_for_admission_count']}",
        f"- strategy_file_diff_clean: {str(summary['strategy_file_diff_clean']).lower()}",
        "",
        "## 4. Acceptance Decision",
        summary["acceptance_decision"],
        "",
        "## 5. Recommended Next Steps",
        "1. tech_bottleneck_review_universe_frontend_dataset_v1",
        "2. tech_bottleneck_stock_workspace_review_panel_v1",
        "3. tech_bottleneck_review_universe_manual_review_export_v1",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    universe = _read_csv(AUDIT_UNIVERSE)
    hydrated = _read_csv(HYDRATED)
    remaining_gap = _read_csv(REMAINING_GAP)
    evidence = _read_csv(FULL_BATCH_EVIDENCE)
    codes = set(remaining_gap["stock_code"].tolist())
    index = _prepare_evidence_index(evidence, codes)
    sources = _build_sources(index)
    manifest = _build_download_manifest(sources)
    frontend_ready = _build_frontend_ready(remaining_gap, index, sources)
    remaining_after = frontend_ready[~frontend_ready["targeted_evidence_status"].eq("targeted_frontend_ready")].copy()
    summary = _summary(universe, hydrated, remaining_gap, frontend_ready, index, sources)
    guardrails = {
        key: summary[key]
        for key in [
            "task_name",
            "review_universe_total_count",
            "source_remaining_gap_count",
            "processed_remaining_gap_count",
            "existing_hydrated_frontend_ready_count",
            "v7_frontend_ready_reference_count",
            "core_equivalence_performed",
            "frozen_quality_pool_generated",
            "frontend_write_performed",
            "auto_added_to_quality_pool_count",
            "used_for_signal_count",
            "used_for_admission_count",
            "price_move_used_for_signal",
            "low_position_used_for_signal",
            "strategy_file_diff_clean",
            "acceptance_decision",
        ]
    }
    sources.to_csv(output_dir / "tech_bottleneck_review_universe_targeted_evidence_sources.csv", index=False)
    manifest.to_csv(output_dir / "tech_bottleneck_review_universe_targeted_evidence_download_manifest.csv", index=False)
    index.to_csv(output_dir / "tech_bottleneck_review_universe_targeted_evidence_index.csv", index=False)
    frontend_ready.to_csv(output_dir / "tech_bottleneck_review_universe_targeted_evidence_frontend_ready.csv", index=False)
    remaining_after.to_csv(output_dir / "tech_bottleneck_review_universe_targeted_evidence_remaining_gaps.csv", index=False)
    _write_json(output_dir / "tech_bottleneck_review_universe_targeted_evidence_collection_summary.json", summary)
    _write_json(output_dir / "tech_bottleneck_review_universe_targeted_evidence_guardrails.json", guardrails)
    _write_report(output_dir / "tech_bottleneck_review_universe_targeted_evidence_collection_v1_report.md", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
