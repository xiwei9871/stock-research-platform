from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_v5_evidence_hydration_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME

AUDIT_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_v1.csv"
)
AUDIT_GAP_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_evidence_gap_queue.csv"
)
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"

FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

SOURCE_DIRECTORIES = [
    "outputs/research/tech_bottleneck_quality_pool_layer_v5",
    "outputs/research/tech_bottleneck_quality_pool_layer_v4",
    "outputs/research/tech_bottleneck_quality_pool_layer_v3",
    "outputs/research/tech_bottleneck_quality_pool_layer_v2",
    "outputs/research/tech_bottleneck_quality_pool_layer_v1",
    "outputs/research/tech_bottleneck_docling_90",
    "outputs/research/tech_bottleneck_primary_source_backfill",
    "outputs/research/tech_bottleneck_market_discovered_closure",
    "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1",
    "outputs/research/tech_bottleneck_latent_manual_review_backfill_batch1_v1",
    "outputs/research/tech_bottleneck_latent_manual_review_standard_backfill_v1",
]

RESULT_SOURCES = [
    {
        "name": "canonical_90_manual_approval",
        "path": "outputs/research/tech_bottleneck_90_manual_approval_consolidation_v1/manual_approval_candidates_88.csv",
    },
    {
        "name": "confirmed_core_manual_approval_package",
        "path": "outputs/research/tech_bottleneck_confirmed_core_pool_manual_approval_v1/confirmed_core_manual_approval_package.csv",
    },
    {
        "name": "likely_core_36_backfill",
        "path": "outputs/research/tech_bottleneck_likely_core_36_primary_source_backfill_v1/likely_core_36_backfill_results.csv",
    },
    {
        "name": "backfill_rerun_v2",
        "path": "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2/primary_source_backfill_rerun_v2_results.csv",
    },
    {
        "name": "expansion_backfill",
        "path": "outputs/research/tech_bottleneck_expansion_queue_primary_source_backfill_v1/expansion_queue_backfill_results.csv",
    },
    {
        "name": "false_negative_rescue_backfill",
        "path": "outputs/research/tech_bottleneck_false_negative_rescue_primary_source_backfill_v1/false_negative_rescue_backfill_results.csv",
    },
    {
        "name": "data_gap_backfill",
        "path": "outputs/research/tech_bottleneck_data_gap_primary_source_backfill_v1/data_gap_backfill_results.csv",
    },
    {
        "name": "latent_batch1_rerun_v2_backfill",
        "path": "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2/latent_backfill_batch1_rerun_v2_results.csv",
    },
    {
        "name": "latent_standard_backfill",
        "path": "outputs/research/tech_bottleneck_latent_standard_backfill_queue_v1/latent_standard_backfill_results.csv",
    },
]

EVIDENCE_SOURCES = [
    {
        "name": "confirmed_core_manual_approval_evidence",
        "path": "outputs/research/tech_bottleneck_confirmed_core_pool_manual_approval_v1/confirmed_core_manual_approval_evidence_index.csv",
    },
    {
        "name": "likely_core_36_evidence",
        "path": "outputs/research/tech_bottleneck_likely_core_36_primary_source_backfill_v1/likely_core_36_primary_source_evidence_matrix.csv",
    },
    {
        "name": "backfill_rerun_v2_evidence",
        "path": "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2/primary_source_backfill_rerun_v2_evidence_matrix.csv",
    },
    {
        "name": "expansion_evidence",
        "path": "outputs/research/tech_bottleneck_expansion_queue_primary_source_backfill_v1/expansion_queue_primary_source_evidence_matrix.csv",
    },
    {
        "name": "false_negative_rescue_evidence",
        "path": "outputs/research/tech_bottleneck_false_negative_rescue_primary_source_backfill_v1/false_negative_rescue_evidence_matrix.csv",
    },
    {
        "name": "data_gap_evidence",
        "path": "outputs/research/tech_bottleneck_data_gap_primary_source_backfill_v1/data_gap_primary_source_evidence_matrix.csv",
    },
    {
        "name": "latent_batch1_rerun_v2_evidence",
        "path": "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2/latent_backfill_batch1_rerun_v2_evidence_matrix.csv",
    },
    {
        "name": "latent_standard_evidence",
        "path": "outputs/research/tech_bottleneck_latent_standard_backfill_queue_v1/latent_standard_evidence_matrix.csv",
    },
]

HYDRATED_COLUMNS = [
    "stock_code",
    "stock_name",
    "review_universe_source",
    "current_layer_status",
    "source_group",
    "proposal_source",
    "hydration_status",
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
    "source_name",
    "source_type",
    "source_title",
    "source_path_or_url",
    "page",
    "claim",
    "supports_field",
    "evidence_strength",
    "is_primary_source",
    "provenance_status",
    "citation_quality",
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
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _maybe_read_csv(relative_path: str) -> pd.DataFrame:
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        return pd.DataFrame()
    return _read_csv(path)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _int_value(value: Any) -> int:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _non_empty(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return default if not text or text.lower() == "nan" else text


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _missing_source_directories() -> list[str]:
    return [relative for relative in SOURCE_DIRECTORIES if not (PROJECT_ROOT / relative).exists()]


def _load_result_frames() -> dict[str, pd.DataFrame]:
    return {source["name"]: _maybe_read_csv(source["path"]) for source in RESULT_SOURCES}


def _load_evidence_index(v5_codes: set[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in EVIDENCE_SOURCES:
        frame = _maybe_read_csv(source["path"])
        if frame.empty:
            continue
        frame = frame[frame["stock_code"].isin(v5_codes)].copy()
        for _, row in frame.sort_values(["stock_code", "page", "source_title"]).iterrows():
            page = _non_empty(row.get("page"))
            provenance = _non_empty(row.get("provenance_status"), "source_level")
            citation_quality = "page_level" if page and "page" in provenance.lower() else provenance
            rows.append(
                {
                    "stock_code": row["stock_code"],
                    "stock_name": row.get("stock_name", ""),
                    "source_name": source["name"],
                    "source_type": row.get("source_type", ""),
                    "source_title": row.get("source_title", ""),
                    "source_path_or_url": row.get("source_path_or_url", row.get("source_file", "")),
                    "page": page,
                    "claim": row.get("claim", row.get("evidence_text", "")),
                    "supports_field": row.get("supports_field", row.get("evidence_claim_type", "")),
                    "evidence_strength": row.get("evidence_strength", ""),
                    "is_primary_source": _truthy(row.get("is_primary_source", True)),
                    "provenance_status": provenance,
                    "citation_quality": citation_quality,
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    index = pd.DataFrame(rows, columns=EVIDENCE_INDEX_COLUMNS)
    if not index.empty:
        index = index.drop_duplicates(
            subset=["stock_code", "source_path_or_url", "page", "claim", "supports_field"],
            keep="first",
        ).sort_values(["stock_code", "source_name", "source_title", "page"])
    return index


def _result_for_stock(result_frames: dict[str, pd.DataFrame], code: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name in [
        "canonical_90_manual_approval",
        "confirmed_core_manual_approval_package",
        "likely_core_36_backfill",
        "backfill_rerun_v2",
        "expansion_backfill",
        "false_negative_rescue_backfill",
        "data_gap_backfill",
        "latent_batch1_rerun_v2_backfill",
        "latent_standard_backfill",
    ]:
        frame = result_frames.get(name, pd.DataFrame())
        if frame.empty or "stock_code" not in frame.columns:
            continue
        match = frame[frame["stock_code"].eq(code)]
        if match.empty:
            continue
        row = match.iloc[0].to_dict()
        for key, value in row.items():
            if key not in merged or _non_empty(value):
                merged[key] = value
        merged["_result_source"] = name
    return merged


def _sum_count(row: dict[str, Any], keys: list[str]) -> int:
    return sum(_int_value(row.get(key)) for key in keys)


def _claim_samples(evidence: pd.DataFrame) -> tuple[str, str]:
    if evidence.empty:
        return "", ""
    strong = evidence[
        evidence["evidence_strength"].astype(str).str.contains("strong", case=False, na=False)
        | evidence["supports_field"].astype(str).str.contains("hard_tech|bottleneck|order|customer|revenue", case=False, na=False)
    ]
    weakest = evidence[
        evidence["supports_field"].astype(str).str.contains("risk|disconfirmation|route", case=False, na=False)
        | evidence["evidence_strength"].astype(str).str.contains("moderate|weak", case=False, na=False)
    ]
    strongest_claim = _non_empty((strong.iloc[0] if not strong.empty else evidence.iloc[0]).get("claim"))
    weakest_claim = _non_empty((weakest.iloc[0] if not weakest.empty else evidence.iloc[-1]).get("claim"))
    return strongest_claim[:500], weakest_claim[:500]


def _source_pdf_count(evidence: pd.DataFrame, result_row: dict[str, Any]) -> int:
    if not evidence.empty:
        paths = [value for value in evidence["source_path_or_url"].astype(str).tolist() if value.strip()]
        if paths:
            return len(set(paths))
    titles = _non_empty(result_row.get("key_primary_source_titles"))
    if titles:
        return len([part for part in titles.split("|") if part.strip()])
    return 0


def _status(evidence_count: int, page_count: int, source_pdf_count: int, supported: bool, has_index: bool) -> str:
    if not supported:
        return "insufficient_existing_artifacts"
    if evidence_count >= 8 and page_count >= 8 and source_pdf_count > 0 and has_index:
        return "hydrated_frontend_ready"
    if evidence_count > 0 and page_count > 0:
        return "hydrated_evidence_light_but_usable"
    if evidence_count > 0:
        return "remaining_needs_manual_source_mapping"
    return "remaining_needs_targeted_collection"


def _build_hydrated(v5: pd.DataFrame, gap: pd.DataFrame, evidence_index: pd.DataFrame, result_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    gap_v5_codes = set(gap.loc[gap["review_universe_source"].eq("v5_existing"), "stock_code"].tolist())
    v5 = v5[v5["stock_code"].isin(gap_v5_codes)].copy()
    evidence_by_code = {code: group.copy() for code, group in evidence_index.groupby("stock_code")}
    rows: list[dict[str, Any]] = []
    for _, v5_row in v5.sort_values("stock_code").iterrows():
        code = v5_row["stock_code"]
        result_row = _result_for_stock(result_frames, code)
        evidence = evidence_by_code.get(code, pd.DataFrame(columns=EVIDENCE_INDEX_COLUMNS))
        evidence_count = max(
            len(evidence),
            _int_value(result_row.get("primary_source_evidence_count")),
            _int_value(result_row.get("page_level_citation_count")),
            _sum_count(
                result_row,
                [
                    "annual_report_evidence_count",
                    "announcement_evidence_count",
                    "official_website_evidence_count",
                    "customer_certification_evidence_count",
                    "order_or_capacity_evidence_count",
                    "revenue_trace_evidence_count",
                    "financial_trace_evidence_count",
                    "interactive_platform_evidence_count",
                ],
            ),
        )
        page_count = max(
            int(evidence["citation_quality"].astype(str).str.contains("page_level", case=False, na=False).sum())
            if not evidence.empty
            else 0,
            _int_value(result_row.get("page_level_citation_count")),
        )
        source_pdf_count = _source_pdf_count(evidence, result_row)
        primary_source_supported = _truthy(result_row.get("primary_source_supported", v5_row.get("primary_source_supported")))
        strongest, weakest = _claim_samples(evidence)
        hard_tech_domain = _non_empty(
            result_row.get("hard_tech_exposure_quality_after_backfill")
            or result_row.get("hard_tech_exposure_quality")
            or result_row.get("bottleneck_thesis_support_after_backfill")
            or v5_row.get("bottleneck_thesis_support"),
            "evidence_required",
        )
        supply_chain_role = _non_empty(
            result_row.get("supply_chain_role_quality_after_backfill") or result_row.get("supply_chain_role_quality"),
            "evidence_required",
        )
        business_relevance = _non_empty(result_row.get("business_relevance_after_backfill"), "evidence_required")
        bottleneck_hint = _non_empty(
            result_row.get("bottleneck_thesis_support_after_backfill") or result_row.get("bottleneck_thesis_support"),
            "evidence_required",
        )
        remaining_gaps = _non_empty(result_row.get("remaining_evidence_gap_flags") or v5_row.get("remaining_evidence_gap_flags"), "")
        hydration_status = _status(evidence_count, page_count, source_pdf_count, primary_source_supported, not evidence.empty)
        rows.append(
            {
                "stock_code": code,
                "stock_name": v5_row.get("stock_name", result_row.get("stock_name", "")),
                "review_universe_source": "v5_existing",
                "current_layer_status": v5_row.get("quality_layer", ""),
                "source_group": v5_row.get("source_group", ""),
                "proposal_source": v5_row.get("proposal_source", ""),
                "hydration_status": hydration_status,
                "evidence_count": int(evidence_count),
                "page_citation_count": int(page_count),
                "source_pdf_count": int(source_pdf_count),
                "primary_source_supported": primary_source_supported,
                "hard_tech_domain": hard_tech_domain,
                "supply_chain_role_hint": supply_chain_role,
                "business_relevance_hint": business_relevance,
                "bottleneck_or_chokepoint_hint": bottleneck_hint,
                "concept_pollution_risk": _non_empty(
                    result_row.get("pollution_risk") or result_row.get("concept_pollution_risk"),
                    "not_detected_in_existing_artifacts",
                ),
                "route_around_or_substitution_risk": _non_empty(
                    result_row.get("route_around_quality_after_backfill")
                    or result_row.get("route_around_or_substitution_risk")
                    or remaining_gaps,
                    "needs_manual_review",
                ),
                "value_capture_risk": _non_empty(
                    result_row.get("value_capture_quality_after_backfill") or result_row.get("value_capture_risk"),
                    "needs_manual_review",
                ),
                "disconfirmation_trigger": _truthy(result_row.get("disconfirmation_found")),
                "next_primary_source_to_check": _non_empty(
                    result_row.get("recommended_next_evidence_action")
                    or result_row.get("recommended_next_action")
                    or v5_row.get("recommended_next_action"),
                    "manual review evidence provenance",
                ),
                "strongest_primary_source_claim": strongest,
                "weakest_or_riskiest_claim": weakest,
                "recommended_next_action": "use hydrated evidence in review dataset"
                if hydration_status == "hydrated_frontend_ready"
                else "target remaining source mapping or page-level evidence hydration",
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
    return pd.DataFrame(rows, columns=HYDRATED_COLUMNS)


def _summary(hydrated: pd.DataFrame, universe: pd.DataFrame, gap: pd.DataFrame, evidence_index: pd.DataFrame, missing_dirs: list[str]) -> dict[str, Any]:
    status_counts = hydrated["hydration_status"].value_counts().sort_index().to_dict()
    duplicate_stock_count = int(hydrated["stock_code"].duplicated().sum())
    strategy_clean = _strategy_diff_clean()
    used_for_signal_count = int(hydrated["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(hydrated["used_for_admission"].astype(bool).sum())
    auto_added_count = int(hydrated["auto_added_to_quality_pool"].astype(bool).sum())
    frontend_ready_count = int(hydrated["hydration_status"].eq("hydrated_frontend_ready").sum())
    remaining_count = int(len(hydrated) - frontend_ready_count)
    guardrail_violation = (
        len(universe) != 378
        or len(gap) != 300
        or len(hydrated) != 300
        or duplicate_stock_count != 0
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or auto_added_count != 0
        or not strategy_clean
    )
    if guardrail_violation:
        decision = "blocked_due_to_guardrail_violation"
    elif remaining_count > 0:
        decision = "conditionally_ready_with_remaining_gaps"
    else:
        decision = "tech_bottleneck_review_universe_v5_evidence_hydration_ready"
    return {
        "task_name": TASK_NAME,
        "review_universe_total_count": int(len(universe)),
        "source_evidence_gap_queue_count": int(len(gap)),
        "processed_v5_gap_count": int(len(hydrated)),
        "v7_frontend_ready_reference_count": int((universe["review_universe_source"] != "v5_existing").sum()),
        "duplicate_stock_count": duplicate_stock_count,
        "hydrated_frontend_ready_count": frontend_ready_count,
        "remaining_gap_count": remaining_count,
        "hydration_status_counts": {key: int(value) for key, value in status_counts.items()},
        "evidence_index_row_count": int(len(evidence_index)),
        "hydrated_page_citation_count": int(hydrated["page_citation_count"].astype(int).sum()),
        "hydrated_source_pdf_count": int(hydrated["source_pdf_count"].astype(int).sum()),
        "missing_source_directory_count": len(missing_dirs),
        "missing_source_directories": missing_dirs,
        "primary_source_collection_performed": False,
        "new_pdf_download_count": 0,
        "evidence_hydration_performed": True,
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
        "# Tech Bottleneck Review Universe V5 Evidence Hydration v1",
        "",
        "## 1. Scope",
        "This research-only hydration step processes only the 300 v5_existing rows in the review-universe evidence gap queue. It reads historical artifacts and does not collect PDFs, run new backfill, run equivalence gates, freeze pools, write frontend files, or connect to signal/admission/scoring/strategy.",
        "",
        "## 2. Input",
        f"- review universe total: {summary['review_universe_total_count']}",
        f"- source evidence gap queue: {summary['source_evidence_gap_queue_count']}",
        f"- processed v5 gap rows: {summary['processed_v5_gap_count']}",
        f"- v7 frontend-ready reference rows not processed: {summary['v7_frontend_ready_reference_count']}",
        "",
        "## 3. Hydration Results",
        f"- hydrated_frontend_ready: {summary['hydrated_frontend_ready_count']}",
        f"- remaining_gap_count: {summary['remaining_gap_count']}",
        f"- evidence_index_row_count: {summary['evidence_index_row_count']}",
        *[f"- {key}: {value}" for key, value in summary["hydration_status_counts"].items()],
        "",
        "## 4. Missing Source Directories",
        *[f"- {path}" for path in summary["missing_source_directories"]],
        "",
        "## 5. Guardrails",
        f"- primary_source_collection_performed: {str(summary['primary_source_collection_performed']).lower()}",
        f"- new_pdf_download_count: {summary['new_pdf_download_count']}",
        f"- core_equivalence_performed: {str(summary['core_equivalence_performed']).lower()}",
        f"- frozen_quality_pool_generated: {str(summary['frozen_quality_pool_generated']).lower()}",
        f"- frontend_write_performed: {str(summary['frontend_write_performed']).lower()}",
        f"- used_for_signal_count: {summary['used_for_signal_count']}",
        f"- used_for_admission_count: {summary['used_for_admission_count']}",
        f"- strategy_file_diff_clean: {str(summary['strategy_file_diff_clean']).lower()}",
        "",
        "## 6. Acceptance Decision",
        summary["acceptance_decision"],
        "",
        "## 7. Recommended Next Steps",
        "1. tech_bottleneck_review_universe_targeted_evidence_collection_v1",
        "2. tech_bottleneck_review_universe_frontend_dataset_v1",
        "3. tech_bottleneck_stock_workspace_review_panel_v1",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    universe = _read_csv(AUDIT_UNIVERSE)
    gap = _read_csv(AUDIT_GAP_QUEUE)
    v5 = _read_csv(V5_MANIFEST)
    v5_gap_codes = set(gap.loc[gap["review_universe_source"].eq("v5_existing"), "stock_code"].tolist())
    evidence_index = _load_evidence_index(v5_gap_codes)
    result_frames = _load_result_frames()
    hydrated = _build_hydrated(v5, gap, evidence_index, result_frames)
    frontend_ready = hydrated[hydrated["hydration_status"].eq("hydrated_frontend_ready")].copy()
    remaining = hydrated[~hydrated["hydration_status"].eq("hydrated_frontend_ready")].copy()
    missing_dirs = _missing_source_directories()
    summary = _summary(hydrated, universe, gap, evidence_index, missing_dirs)
    guardrails = {
        key: summary[key]
        for key in [
            "task_name",
            "review_universe_total_count",
            "source_evidence_gap_queue_count",
            "processed_v5_gap_count",
            "v7_frontend_ready_reference_count",
            "duplicate_stock_count",
            "primary_source_collection_performed",
            "new_pdf_download_count",
            "evidence_hydration_performed",
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

    hydrated.to_csv(output_dir / "tech_bottleneck_review_universe_v5_evidence_hydrated.csv", index=False)
    evidence_index.to_csv(output_dir / "tech_bottleneck_review_universe_v5_evidence_index.csv", index=False)
    frontend_ready.to_csv(output_dir / "tech_bottleneck_review_universe_v5_hydrated_frontend_ready.csv", index=False)
    remaining.to_csv(output_dir / "tech_bottleneck_review_universe_v5_remaining_gap_queue.csv", index=False)
    _write_json(output_dir / "tech_bottleneck_review_universe_v5_evidence_hydration_summary.json", summary)
    _write_json(
        output_dir / "tech_bottleneck_review_universe_v5_missing_source_directories.json",
        {"missing_source_directories": missing_dirs},
    )
    _write_json(output_dir / "tech_bottleneck_review_universe_v5_evidence_hydration_guardrails.json", guardrails)
    _write_report(output_dir / "tech_bottleneck_review_universe_v5_evidence_hydration_v1_report.md", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
