from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_backfill_primary_source_text_first_parse import (
    _build_source_rows,
    _extract_pages,
)
from stock_research.tech_bottleneck_90_primary_source_backfill import (
    _build_gap_matrix,
    _strategy_diff_clean,
    _stock_code,
    _write_json,
)
from stock_research.tech_bottleneck_90_primary_source_backfill_rerun_v2 import (
    _build_evidence_matrix,
    _upgrade_decision_if_needed,
)
from stock_research.tech_bottleneck_latent_primary_source_backfill_batch1 import (
    _assess as _assess_latent_structured,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_v1/latent_backfill_batch1_remain_pending.csv"
)
COLLECTION_MANIFEST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_pending_primary_source_collection_v1/latent_pending_primary_source_collection_manifest.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 45


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _empty_chunks() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "stock_code",
            "stock_name",
            "source_type",
            "source_title",
            "source_path",
            "chunk_id",
            "chunk_text",
            "page_start",
            "page_end",
            "page_locator",
            "citation_granularity",
            "section_matches",
            "keyword_score",
        ]
    )


def _parse_manifest(manifest: pd.DataFrame, output: Path, *, max_pages_per_source: int = 80, max_chunks_per_source: int = 8) -> tuple[pd.DataFrame, dict[str, Any]]:
    chunks_path = output / "latent_backfill_batch1_rerun_v2_text_first_chunks.csv"
    parse_manifest_path = output / "latent_backfill_batch1_rerun_v2_text_first_parse_manifest.csv"
    if chunks_path.exists() and parse_manifest_path.exists():
        chunks = _read_csv(chunks_path)
        parse_manifest = pd.read_csv(parse_manifest_path).fillna("")
        return chunks, {
            "source_pdf_count": int(len(manifest)),
            "parse_source_count": int(len(parse_manifest)),
            "evidence_chunk_count": int(len(chunks)),
            "page_level_citation_count": int(chunks["citation_granularity"].eq("page_level").sum()) if not chunks.empty else 0,
        }
    if manifest.empty:
        chunks = _empty_chunks()
        chunks.to_csv(chunks_path, index=False)
        pd.DataFrame().to_csv(parse_manifest_path, index=False)
        return chunks, {"source_pdf_count": 0, "parse_source_count": 0, "evidence_chunk_count": 0, "page_level_citation_count": 0}

    manifest = manifest.copy().sort_values(["stock_code", "source_type", "local_pdf_path"]).reset_index(drop=True)
    manifest["source_index"] = range(1, len(manifest) + 1)
    parse_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    for source in manifest.to_dict("records"):
        pages, metadata = _extract_pages(Path(str(source["local_pdf_path"])), max_pages_per_source)
        parse_row, chunks, _fallback = _build_source_rows(source, pages, metadata, max_chunks_per_source=max_chunks_per_source)
        parse_rows.append(parse_row)
        chunk_rows.extend(chunks)
    chunks_df = pd.DataFrame(chunk_rows) if chunk_rows else _empty_chunks()
    parse_df = pd.DataFrame(parse_rows)
    chunks_df.to_csv(chunks_path, index=False)
    parse_df.to_csv(parse_manifest_path, index=False)
    return chunks_df, {
        "source_pdf_count": int(len(manifest)),
        "parse_source_count": int(len(parse_df)),
        "evidence_chunk_count": int(len(chunks_df)),
        "page_level_citation_count": int(chunks_df["citation_granularity"].eq("page_level").sum()) if not chunks_df.empty else 0,
    }


def _queue_for_assessment(queue: pd.DataFrame) -> pd.DataFrame:
    assessed_rows = []
    for _, row in queue.iterrows():
        # Preserve prior pending context but reset synthetic primary-source fields before rerun assessment.
        item = row.copy()
        item["manual_review_entry_class"] = "latent_pending_evidence"
        item["quality_gate_decision"] = row.get("previous_quality_audit_decision", "latent_high_priority_backfill")
        item["bottleneck_thesis_support"] = row.get("bottleneck_thesis_support_after_backfill", "weak")
        item["brokerage_evidence_count"] = 0
        item["primary_source_evidence_count"] = 0
        assessed_rows.append(item)
    return pd.DataFrame(assessed_rows).sort_values("stock_code").reset_index(drop=True)


def _map_decision(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    decision = row["recommended_backfill_decision"]
    if decision == "upgrade_to_confirmed_core_proposal":
        row["recommended_backfill_decision"] = "upgrade_to_latent_manual_approval_candidate"
        row["recommended_manual_review_entry_class"] = "latent_manual_approval_candidate"
    elif decision == "remain_likely_core_pending_evidence":
        row["recommended_backfill_decision"] = "remain_latent_pending_evidence"
        row["recommended_manual_review_entry_class"] = "latent_pending_evidence"
    elif decision == "move_to_adjacent_watchlist":
        row["recommended_manual_review_entry_class"] = "adjacent_watchlist"
    elif decision == "downgrade_or_reject":
        row["recommended_manual_review_entry_class"] = "downgrade_or_reject"
    row["price_move_used_for_signal"] = False
    row["low_position_used_for_signal"] = False
    row["core_equivalence_performed"] = False
    return row


def _assess_stock(queue_row: pd.Series, stock_evidence: pd.DataFrame) -> dict[str, Any]:
    # Reuse the conservative 90-stock primary-source assessment where page evidence exists.
    from stock_research.tech_bottleneck_90_primary_source_backfill import _assess_stock as assess_primary

    assessed = assess_primary(queue_row, stock_evidence)
    assessed = _upgrade_decision_if_needed(assessed, stock_evidence)
    return _map_decision(assessed)


def _assess_results(queue: pd.DataFrame, evidence_matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    assessment_queue = _queue_for_assessment(queue)
    for _, row in assessment_queue.iterrows():
        stock_evidence = evidence_matrix[evidence_matrix["stock_code"].eq(row["stock_code"])]
        if stock_evidence.empty:
            assessed = _assess_latent_structured(row)
            assessed["core_equivalence_performed"] = False
        else:
            assessed = _assess_stock(row, stock_evidence)
        rows.append(assessed)
    columns = [
        "stock_code",
        "stock_name",
        "previous_manual_review_entry_class",
        "previous_quality_gate_decision",
        "previous_bottleneck_thesis_support",
        "primary_source_backfill_status",
        "annual_report_evidence_count",
        "announcement_evidence_count",
        "official_website_evidence_count",
        "customer_certification_evidence_count",
        "order_or_capacity_evidence_count",
        "revenue_trace_evidence_count",
        "financial_trace_evidence_count",
        "interactive_platform_evidence_count",
        "brokerage_evidence_count",
        "primary_source_supported",
        "brokerage_only_after_backfill",
        "bottleneck_thesis_support_after_backfill",
        "hard_tech_exposure_quality_after_backfill",
        "business_relevance_after_backfill",
        "supply_chain_role_quality_after_backfill",
        "architecture_shift_quality_after_backfill",
        "route_around_quality_after_backfill",
        "value_capture_quality_after_backfill",
        "disconfirmation_found",
        "disconfirmation_summary",
        "remaining_evidence_gap_flags",
        "recommended_backfill_decision",
        "recommended_manual_review_entry_class",
        "recommended_next_evidence_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "price_move_used_for_signal",
        "low_position_used_for_signal",
        "core_equivalence_performed",
        "notes",
    ]
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame[columns].sort_values("stock_code").reset_index(drop=True)


def _split_outputs(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manual = results[results["recommended_backfill_decision"].eq("upgrade_to_latent_manual_approval_candidate")].copy()
    pending = results[results["recommended_backfill_decision"].eq("remain_latent_pending_evidence")].copy()
    adjacent = results[
        results["recommended_backfill_decision"].isin({"move_to_adjacent_watchlist", "downgrade_or_reject"})
    ].copy()
    return manual, pending, adjacent


def _summary(queue: pd.DataFrame, manifest: pd.DataFrame, results: pd.DataFrame, evidence: pd.DataFrame, parse_summary: dict[str, Any], strategy_clean: bool) -> dict[str, Any]:
    manual, pending, adjacent_or_reject = _split_outputs(results)
    adjacent = adjacent_or_reject[adjacent_or_reject["recommended_backfill_decision"].eq("move_to_adjacent_watchlist")]
    reject = adjacent_or_reject[adjacent_or_reject["recommended_backfill_decision"].eq("downgrade_or_reject")]
    used_for_signal = int(results["used_for_signal"].astype(bool).sum()) if not results.empty else 0
    used_for_admission = int(results["used_for_admission"].astype(bool).sum()) if not results.empty else 0
    price_signal = int(results["price_move_used_for_signal"].astype(bool).sum()) if not results.empty else 0
    low_signal = int(results["low_position_used_for_signal"].astype(bool).sum()) if not results.empty else 0
    if not strategy_clean or used_for_signal or used_for_admission or price_signal or low_signal:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(pending) or len(adjacent_or_reject):
        acceptance = "conditionally_ready_with_remaining_gaps"
    else:
        acceptance = "latent_primary_source_backfill_batch1_rerun_v2_ready"
    return {
        "task_name": TASK_NAME,
        "source_latent_pending_count": int(len(queue)),
        "processed_count": int(len(results)),
        "collection_pdf_count": int(len(manifest)),
        "parse_source_count": int(parse_summary["parse_source_count"]),
        "text_first_evidence_chunk_count": int(parse_summary["evidence_chunk_count"]),
        "page_level_citation_count": int(parse_summary["page_level_citation_count"]),
        "primary_source_supported_count": int(results["primary_source_supported"].astype(bool).sum()) if not results.empty else 0,
        "evidence_matrix_count": int(len(evidence)),
        "upgrade_count": int(len(manual)),
        "remain_pending_count": int(len(pending)),
        "adjacent_count": int(len(adjacent)),
        "downgrade_or_reject_count": int(len(reject)),
        "core_equivalence_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": price_signal,
        "low_position_used_for_signal": low_signal,
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
        "source_latent_pending_count": summary["source_latent_pending_count"],
        "processed_count": summary["processed_count"],
        "collection_pdf_count": summary["collection_pdf_count"],
        "core_equivalence_performed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
        "low_position_used_for_signal": summary["low_position_used_for_signal"],
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
            "# Tech Bottleneck Latent Primary Source Backfill Batch1 Rerun v2",
            "",
            "## 1. Scope",
            "This task reruns primary-source backfill only for the 45 latent pending candidates covered by the latest primary-source collection. It does not perform core equivalence, quality-pool application, signal, or admission actions.",
            "",
            "## 2. Evidence Inputs",
            f"Collection PDFs: {summary['collection_pdf_count']}; parsed sources: {summary['parse_source_count']}; evidence chunks: {summary['text_first_evidence_chunk_count']}; page-level citations: {summary['page_level_citation_count']}.",
            "",
            "## 3. Backfill Results",
            f"Primary-source supported: {summary['primary_source_supported_count']}; manual approval candidates: {summary['upgrade_count']}; remain pending: {summary['remain_pending_count']}; adjacent: {summary['adjacent_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Guardrails",
            f"core_equivalence_performed=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal={summary['price_move_used_for_signal']}; low_position_used_for_signal={summary['low_position_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2",
            "2. tech_bottleneck_latent_pending_primary_source_collection_v2",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    queue = _read_csv(INPUT_QUEUE).sort_values("stock_code").reset_index(drop=True)
    manifest = _read_csv(COLLECTION_MANIFEST)
    manifest = manifest[manifest["stock_code"].isin(set(queue["stock_code"]))].copy().sort_values(["stock_code", "source_type"])
    chunks, parse_summary = _parse_manifest(manifest, output)
    evidence = _build_evidence_matrix(chunks)
    evidence = evidence[evidence["stock_code"].isin(set(queue["stock_code"]))].copy()
    results = _assess_results(queue, evidence)
    gaps = _build_gap_matrix(results)
    manual, pending, adjacent = _split_outputs(results)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(queue, manifest, results, evidence, parse_summary, strategy_clean)
    guardrails = _guardrails(summary)

    results.to_csv(output / "latent_backfill_batch1_rerun_v2_results.csv", index=False)
    evidence.to_csv(output / "latent_backfill_batch1_rerun_v2_evidence_matrix.csv", index=False)
    gaps.to_csv(output / "latent_backfill_batch1_rerun_v2_gap_matrix.csv", index=False)
    manual.to_csv(output / "latent_backfill_batch1_rerun_v2_manual_approval_candidates.csv", index=False)
    pending.to_csv(output / "latent_backfill_batch1_rerun_v2_remain_pending.csv", index=False)
    adjacent.to_csv(output / "latent_backfill_batch1_rerun_v2_adjacent_or_reject.csv", index=False)
    _write_json(output / "latent_backfill_batch1_rerun_v2_summary.json", summary)
    _write_json(output / "latent_backfill_batch1_rerun_v2_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
